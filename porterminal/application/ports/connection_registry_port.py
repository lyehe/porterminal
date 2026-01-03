"""Connection registry port - interface for broadcasting to user connections."""

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from porterminal.domain import UserId

    from .connection_port import ConnectionPort


class ConnectionRegistryPort(Protocol):
    """Protocol for managing and broadcasting to user connections.

    Infrastructure layer (e.g., UserConnectionRegistry) implements this.
    Application layer uses this interface for broadcasting messages.
    """

    async def register(self, user_id: "UserId", connection: "ConnectionPort") -> None:
        """Register a new connection for a user."""
        ...

    async def unregister(self, user_id: "UserId", connection: "ConnectionPort") -> None:
        """Unregister a connection."""
        ...

    async def broadcast(
        self,
        user_id: "UserId",
        message: dict[str, Any],
        exclude: "ConnectionPort | None" = None,
    ) -> int:
        """Send message to all connections for a user.

        Args:
            user_id: User to broadcast to.
            message: Message dict to send.
            exclude: Optional connection to exclude (e.g., the sender).

        Returns:
            Number of connections sent to.
        """
        ...

    def total_connections(self) -> int:
        """Get total number of connections across all users."""
        ...
