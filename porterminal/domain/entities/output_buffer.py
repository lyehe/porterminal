"""Output buffer entity for session reconnection."""

from collections import deque
from dataclasses import dataclass, field

# Business rules
OUTPUT_BUFFER_MAX_BYTES = 1_000_000  # 1MB

# Terminal escape sequence for clear screen (ED2)
CLEAR_SCREEN_SEQUENCE = b"\x1b[2J"


@dataclass
class OutputBuffer:
    """Output buffer for session reconnection.

    Pure domain logic for buffering terminal output.
    No async, no WebSocket - just data management.
    """

    max_bytes: int = OUTPUT_BUFFER_MAX_BYTES
    _buffer: deque[bytes] = field(default_factory=deque)
    _size: int = 0

    @property
    def size(self) -> int:
        """Current buffer size in bytes."""
        return self._size

    @property
    def is_empty(self) -> bool:
        """Check if buffer is empty."""
        return self._size == 0

    def add(self, data: bytes) -> None:
        """Add data to the buffer.

        Handles clear screen detection and size limits.
        """
        # Clear on screen reset (business rule)
        if CLEAR_SCREEN_SEQUENCE in data:
            self.clear()

        self._buffer.append(data)
        self._size += len(data)

        # Trim if over limit
        while self._size > self.max_bytes and self._buffer:
            removed = self._buffer.popleft()
            self._size -= len(removed)

    def get_all(self) -> bytes:
        """Get all buffered output as single bytes object."""
        return b"".join(self._buffer)

    def clear(self) -> None:
        """Clear the buffer."""
        self._buffer.clear()
        self._size = 0

    def __len__(self) -> int:
        """Return number of chunks in buffer."""
        return len(self._buffer)
