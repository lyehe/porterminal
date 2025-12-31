"""User connection registry for broadcasting tab sync messages."""

import asyncio
import logging
from typing import Any

from porterminal.application.ports import ConnectionPort
from porterminal.domain import UserId

logger = logging.getLogger(__name__)


class UserConnectionRegistry:
    """Track all WebSocket connections per user for broadcasting.

    Enables real-time tab sync across multiple browser windows/devices.
    Thread-safe for async usage.
    """

    def __init__(self) -> None:
        self._connections: dict[str, set[ConnectionPort]] = {}
        self._lock = asyncio.Lock()

    async def register(self, user_id: UserId, connection: ConnectionPort) -> None:
        """Register a new connection for a user."""
        user_str = str(user_id)
        async with self._lock:
            if user_str not in self._connections:
                self._connections[user_str] = set()
            self._connections[user_str].add(connection)
            logger.debug(
                "Connection registered user_id=%s total=%d",
                user_str,
                len(self._connections[user_str]),
            )

    async def unregister(self, user_id: UserId, connection: ConnectionPort) -> None:
        """Unregister a connection."""
        user_str = str(user_id)
        async with self._lock:
            if user_str in self._connections:
                self._connections[user_str].discard(connection)
                if not self._connections[user_str]:
                    del self._connections[user_str]
                logger.debug("Connection unregistered user_id=%s", user_str)

    async def broadcast(
        self,
        user_id: UserId,
        message: dict[str, Any],
        exclude: ConnectionPort | None = None,
    ) -> int:
        """Send message to all connections for a user.

        Args:
            user_id: User to broadcast to.
            message: Message dict to send.
            exclude: Optional connection to exclude (e.g., the sender).

        Returns:
            Number of connections sent to.
        """
        user_str = str(user_id)

        async with self._lock:
            connections = self._connections.get(user_str, set()).copy()

        if exclude:
            connections.discard(exclude)

        if not connections:
            return 0

        # Send in parallel
        async def send_one(conn: ConnectionPort) -> bool:
            try:
                await conn.send_message(message)
                return True
            except Exception as e:
                logger.warning("Failed to broadcast to connection: %s", e)
                return False

        results = await asyncio.gather(
            *[send_one(conn) for conn in connections],
            return_exceptions=True,
        )
        count = sum(1 for r in results if r is True)

        logger.debug(
            "Broadcast to user_id=%s sent=%d/%d type=%s",
            user_str,
            count,
            len(connections),
            message.get("type"),
        )
        return count

    def connection_count(self, user_id: UserId) -> int:
        """Get number of connections for a user."""
        return len(self._connections.get(str(user_id), set()))

    def total_connections(self) -> int:
        """Get total number of connections across all users."""
        return sum(len(conns) for conns in self._connections.values())
