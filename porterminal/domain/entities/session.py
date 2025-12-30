"""Session entity - pure domain representation."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import TypeVar

from ..values.session_id import SessionId
from ..values.terminal_dimensions import TerminalDimensions
from ..values.user_id import UserId
from .output_buffer import OutputBuffer

# Generic type for PTY handle - infrastructure provides concrete type
PTYHandle = TypeVar("PTYHandle")

# Business rule constants
MAX_SESSIONS_PER_USER = 10
MAX_TOTAL_SESSIONS = 100
RECONNECT_WINDOW_SECONDS = 0  # 0 = unlimited
SESSION_MAX_DURATION_SECONDS = 0  # 0 = unlimited


@dataclass
class Session[PTYHandle]:
    """Terminal session entity.

    This is the domain representation of a session.
    It does NOT hold WebSocket or any infrastructure references.
    The PTYHandle is a generic type provided by infrastructure.
    """

    id: SessionId
    user_id: UserId
    shell_id: str
    dimensions: TerminalDimensions
    created_at: datetime
    last_activity: datetime

    # PTY handle is generic - concrete type provided by infrastructure
    pty_handle: PTYHandle

    # Output buffer for reconnection
    output_buffer: OutputBuffer = field(default_factory=OutputBuffer)

    # Connection state (managed by application layer)
    # Tracks number of connected clients (supports multi-client sessions)
    connected_clients: int = 0

    def add_client(self) -> int:
        """Add a client connection, return new count."""
        self.connected_clients += 1
        return self.connected_clients

    def remove_client(self) -> int:
        """Remove a client connection, return new count."""
        self.connected_clients = max(0, self.connected_clients - 1)
        return self.connected_clients

    @property
    def is_connected(self) -> bool:
        """Check if any clients connected."""
        return self.connected_clients > 0

    def touch(self, now: datetime) -> None:
        """Update last activity timestamp."""
        self.last_activity = now

    def update_dimensions(self, dimensions: TerminalDimensions) -> None:
        """Update terminal dimensions."""
        self.dimensions = dimensions

    def add_output(self, data: bytes) -> None:
        """Add output to buffer for reconnection."""
        self.output_buffer.add(data)

    def get_buffered_output(self) -> bytes:
        """Get all buffered output."""
        return self.output_buffer.get_all()

    def clear_buffer(self) -> None:
        """Clear the output buffer."""
        self.output_buffer.clear()

    @property
    def session_id(self) -> str:
        """Get session ID as string (compatibility helper)."""
        return str(self.id)
