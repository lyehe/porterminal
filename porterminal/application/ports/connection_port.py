"""Connection port - interface for terminal network connections."""

from typing import Protocol


class ConnectionPort(Protocol):
    """Protocol for terminal I/O over network connection.

    Presentation layer (e.g., WebSocket adapter) implements this.
    """

    async def send_output(self, data: bytes) -> None:
        """Send terminal output to client."""
        ...

    async def send_message(self, message: dict) -> None:
        """Send JSON control message to client."""
        ...

    async def receive(self) -> dict | bytes:
        """Receive message from client (binary or JSON).

        Returns:
            bytes for terminal input, dict for control messages.
        """
        ...

    async def close(self, code: int = 1000, reason: str = "") -> None:
        """Close the connection."""
        ...

    def is_connected(self) -> bool:
        """Check if connection is still open."""
        ...
