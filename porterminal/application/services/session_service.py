"""Session service - session lifecycle management."""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from porterminal.domain import (
    PTYPort,
    Session,
    SessionId,
    SessionLimitChecker,
    ShellCommand,
    TerminalDimensions,
    UserId,
)
from porterminal.domain.ports import SessionRepository

logger = logging.getLogger(__name__)


class SessionService:
    """Service for managing terminal sessions.

    Handles session creation, reconnection, destruction, and cleanup.
    """

    def __init__(
        self,
        repository: SessionRepository[PTYPort],
        pty_factory: Callable[[ShellCommand, TerminalDimensions, str | None], PTYPort],
        limit_checker: SessionLimitChecker | None = None,
        working_directory: str | None = None,
    ) -> None:
        self._repository = repository
        self._pty_factory = pty_factory
        self._limit_checker = limit_checker or SessionLimitChecker()
        self._cwd = working_directory
        self._running = False
        self._cleanup_task: asyncio.Task | None = None
        self._on_session_destroyed: Callable[[SessionId, UserId], Awaitable[None]] | None = None

    def set_on_session_destroyed(
        self, callback: Callable[[SessionId, UserId], Awaitable[None]]
    ) -> None:
        """Set async callback to be invoked when a session is destroyed.

        Used for cascading cleanup (e.g., closing associated tabs and broadcasting).
        """
        self._on_session_destroyed = callback

    async def start(self) -> None:
        """Start the session service (cleanup loop)."""
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Session service started")

    async def stop(self) -> None:
        """Stop the session service and cleanup all sessions."""
        self._running = False

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Close all sessions
        for session in self._repository.all_sessions():
            await self.destroy_session(session.id)

        logger.info("Session service stopped")

    async def create_session(
        self,
        user_id: UserId,
        shell: ShellCommand,
        dimensions: TerminalDimensions,
    ) -> Session[PTYPort]:
        """Create a new terminal session.

        Args:
            user_id: User requesting the session.
            shell: Shell command to run.
            dimensions: Initial terminal dimensions.

        Returns:
            Created session.

        Raises:
            ValueError: If session limits exceeded.
        """
        # Check limits
        limit_result = self._limit_checker.can_create_session(
            user_id,
            self._repository.count_for_user(user_id),
            self._repository.count(),
        )
        if not limit_result.allowed:
            raise ValueError(limit_result.reason)

        # Create PTY (environment sanitization handled by PTY layer)
        pty = self._pty_factory(shell, dimensions, self._cwd)

        # Create session (starts with 0 clients, caller adds via add_client())
        now = datetime.now(UTC)
        session = Session(
            id=SessionId(str(uuid.uuid4())),
            user_id=user_id,
            shell_id=shell.id,
            dimensions=dimensions,
            created_at=now,
            last_activity=now,
            pty_handle=pty,
        )

        self._repository.add(session)
        logger.info(
            "Session created session_id=%s user_id=%s shell=%s",
            session.id,
            user_id,
            shell.id,
        )

        return session

    async def reconnect_session(
        self,
        session_id: SessionId,
        user_id: UserId,
    ) -> Session[PTYPort] | None:
        """Reconnect to an existing session.

        Args:
            session_id: Session to reconnect to.
            user_id: User requesting reconnection.

        Returns:
            Session if reconnection successful, None otherwise.
        """
        session = self._repository.get(session_id)
        if not session:
            logger.warning("Reconnect failed: session not found session_id=%s", session_id)
            return None

        # Check ownership
        limit_result = self._limit_checker.can_reconnect(session, user_id)
        if not limit_result.allowed:
            logger.warning(
                "Reconnect denied: %s session_id=%s user_id=%s",
                limit_result.reason,
                session_id,
                user_id,
            )
            return None

        # Check if PTY is still alive
        if not session.pty_handle.is_alive():
            logger.warning("Reconnect failed: PTY dead session_id=%s", session_id)
            await self.destroy_session(session_id)
            return None

        session.add_client()
        session.touch(datetime.now(UTC))
        logger.info("Session reconnected session_id=%s user_id=%s", session_id, user_id)

        return session

    def disconnect_session(self, session_id: SessionId) -> None:
        """Remove a client from session (but keep alive for reconnection)."""
        session = self._repository.get(session_id)
        if session:
            remaining = session.remove_client()
            session.touch(datetime.now(UTC))
            logger.info(
                "Client disconnected session_id=%s remaining_clients=%d",
                session_id,
                remaining,
            )

    async def destroy_session(self, session_id: SessionId) -> None:
        """Destroy a session completely."""
        session = self._repository.remove(session_id)
        if session:
            # Invoke cascade callback (e.g., to close associated tabs)
            if self._on_session_destroyed:
                try:
                    await self._on_session_destroyed(session_id, session.user_id)
                except Exception as e:
                    logger.warning(
                        "Error in session destroyed callback session_id=%s: %s",
                        session_id,
                        e,
                    )

            try:
                session.pty_handle.close()
            except Exception as e:
                logger.warning("Error closing PTY session_id=%s: %s", session_id, e)

            session.clear_buffer()
            logger.info("Session destroyed session_id=%s", session_id)

    def get_session(self, session_id: str) -> Session[PTYPort] | None:
        """Get session by ID string."""
        return self._repository.get_by_id_str(session_id)

    def get_user_sessions(self, user_id: UserId) -> list[Session[PTYPort]]:
        """Get all sessions for a user."""
        return self._repository.get_by_user(user_id)

    def session_count(self) -> int:
        """Get total session count."""
        return self._repository.count()

    async def _cleanup_loop(self) -> None:
        """Background task to cleanup stale sessions."""
        while self._running:
            await asyncio.sleep(60)
            await self._cleanup_stale_sessions()

    async def _cleanup_stale_sessions(self) -> None:
        """Check and cleanup stale sessions."""
        now = datetime.now(UTC)

        for session in self._repository.all_sessions():
            should_cleanup, reason = self._limit_checker.should_cleanup_session(
                session,
                now,
                session.pty_handle.is_alive(),
            )

            if should_cleanup:
                logger.info(
                    "Cleaning up session session_id=%s reason=%s",
                    session.id,
                    reason,
                )
                await self.destroy_session(session.id)
