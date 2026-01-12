"""Management service - handles tab management requests via WebSocket."""

import logging
from collections.abc import Callable

from porterminal.application.ports import ConnectionPort, ConnectionRegistryPort
from porterminal.application.services.session_service import SessionService
from porterminal.application.services.tab_service import TabService
from porterminal.domain import (
    ShellCommand,
    TerminalDimensions,
    UserId,
)

logger = logging.getLogger(__name__)


class ManagementService:
    """Service for handling management WebSocket messages.

    Handles tab creation, closure, and rename requests.
    Broadcasts state updates to other connections.
    """

    def __init__(
        self,
        session_service: SessionService,
        tab_service: TabService,
        connection_registry: ConnectionRegistryPort,
        shell_provider: Callable[[str | None], ShellCommand | None],
        default_dimensions: TerminalDimensions,
    ) -> None:
        self._session_service = session_service
        self._tab_service = tab_service
        self._registry = connection_registry
        self._get_shell = shell_provider
        self._default_dims = default_dimensions

    async def _send_error(
        self,
        connection: ConnectionPort,
        response_type: str,
        request_id: str,
        error: str,
    ) -> None:
        """Send an error response to a connection."""
        await connection.send_message(
            {
                "type": response_type,
                "request_id": request_id,
                "success": False,
                "error": error,
            }
        )

    async def handle_message(
        self,
        user_id: UserId,
        connection: ConnectionPort,
        message: dict,
    ) -> None:
        """Handle an incoming management message.

        Args:
            user_id: User sending the message.
            connection: Connection that received the message.
            message: Message dict with 'type' and request data.
        """
        msg_type = message.get("type")

        if msg_type == "create_tab":
            await self._handle_create_tab(user_id, connection, message)
        elif msg_type == "close_tab":
            await self._handle_close_tab(user_id, connection, message)
        elif msg_type == "rename_tab":
            await self._handle_rename_tab(user_id, connection, message)
        elif msg_type == "ping":
            await connection.send_message({"type": "pong"})
        else:
            logger.warning("Unknown management message type: %s", msg_type)

    async def _handle_create_tab(
        self,
        user_id: UserId,
        connection: ConnectionPort,
        message: dict,
    ) -> None:
        """Handle tab creation request."""
        request_id = message.get("request_id", "")
        shell_id = message.get("shell_id")

        try:
            # Get shell
            shell = self._get_shell(shell_id)
            if not shell:
                await self._send_error(
                    connection, "create_tab_response", request_id, "Invalid shell"
                )
                return

            # Create session
            session = await self._session_service.create_session(
                user_id=user_id,
                shell=shell,
                dimensions=self._default_dims,
            )
            session.add_client()

            # Create tab
            tab = self._tab_service.create_tab(
                user_id=user_id,
                session_id=session.id,
                shell_id=shell.id,
            )

            logger.info(
                "Management created tab user_id=%s tab_id=%s session_id=%s",
                user_id,
                tab.tab_id,
                session.session_id,
            )

            # Send response to requester
            await connection.send_message(
                {
                    "type": "create_tab_response",
                    "request_id": request_id,
                    "success": True,
                    "tab": tab.to_dict(),
                }
            )

            # Broadcast update to OTHER connections
            await self._registry.broadcast(
                user_id,
                self._tab_service.build_tab_state_update("add", tab),
                exclude=connection,
            )

        except ValueError as e:
            logger.warning("Tab creation failed: %s", e)
            await self._send_error(connection, "create_tab_response", request_id, str(e))

    async def _handle_close_tab(
        self,
        user_id: UserId,
        connection: ConnectionPort,
        message: dict,
    ) -> None:
        """Handle tab close request."""
        request_id = message.get("request_id", "")
        tab_id = message.get("tab_id")

        if not tab_id:
            await self._send_error(connection, "close_tab_response", request_id, "Missing tab_id")
            return

        # Get tab and session info before closing
        tab = self._tab_service.get_tab(tab_id)
        if not tab:
            await self._send_error(connection, "close_tab_response", request_id, "Tab not found")
            return

        session_id = tab.session_id

        # Close the tab
        closed_tab = self._tab_service.close_tab(tab_id, user_id)
        if not closed_tab:
            await self._send_error(
                connection, "close_tab_response", request_id, "Failed to close tab"
            )
            return

        # Destroy the session (which will stop the PTY)
        await self._session_service.destroy_session(session_id)

        logger.info(
            "Management closed tab user_id=%s tab_id=%s",
            user_id,
            tab_id,
        )

        # Send response to requester
        await connection.send_message(
            {
                "type": "close_tab_response",
                "request_id": request_id,
                "success": True,
            }
        )

        # Broadcast update to OTHER connections
        await self._registry.broadcast(
            user_id,
            self._tab_service.build_tab_state_update("remove", closed_tab, reason="user"),
            exclude=connection,
        )

    async def _handle_rename_tab(
        self,
        user_id: UserId,
        connection: ConnectionPort,
        message: dict,
    ) -> None:
        """Handle tab rename request."""
        request_id = message.get("request_id", "")
        tab_id = message.get("tab_id")
        new_name = message.get("name")

        if not tab_id or not new_name:
            await self._send_error(
                connection, "rename_tab_response", request_id, "Missing tab_id or name"
            )
            return

        # Rename the tab
        tab = self._tab_service.rename_tab(tab_id, user_id, new_name)
        if not tab:
            await self._send_error(
                connection, "rename_tab_response", request_id, "Failed to rename tab"
            )
            return

        logger.info(
            "Management renamed tab user_id=%s tab_id=%s new_name=%s",
            user_id,
            tab_id,
            new_name,
        )

        # Send response to requester
        await connection.send_message(
            {
                "type": "rename_tab_response",
                "request_id": request_id,
                "success": True,
                "tab": tab.to_dict(),
            }
        )

        # Broadcast update to OTHER connections
        await self._registry.broadcast(
            user_id,
            self._tab_service.build_tab_state_update("update", tab),
            exclude=connection,
        )

    def build_state_sync(self, user_id: UserId) -> dict:
        """Build initial state sync message for a user.

        Returns:
            Message dict with all tabs for the user.
        """
        return self._tab_service.build_tab_state_sync(user_id)
