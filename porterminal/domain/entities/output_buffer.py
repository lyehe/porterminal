"""Output buffer entity for session reconnection."""

from collections import deque
from dataclasses import dataclass, field

# Business rules
OUTPUT_BUFFER_MAX_BYTES = 1_000_000  # 1MB

# Terminal escape sequence for clear screen (ED2)
CLEAR_SCREEN_SEQUENCE = b"\x1b[2J"

# Alternate screen buffer sequences (DEC Private Mode)
# Used by vim, htop, less, tmux, etc.
ALT_SCREEN_ENTER = (b"\x1b[?47h", b"\x1b[?1047h", b"\x1b[?1049h")
ALT_SCREEN_EXIT = (b"\x1b[?47l", b"\x1b[?1047l", b"\x1b[?1049l")


@dataclass
class OutputBuffer:
    """Output buffer for session reconnection.

    Pure domain logic for buffering terminal output.
    No async, no WebSocket - just data management.

    Handles alternate screen buffer (used by vim, htop, less, etc.):
    - On alt-screen enter: snapshots normal buffer, clears for alt content
    - On alt-screen exit: restores normal buffer, discards alt content
    """

    max_bytes: int = OUTPUT_BUFFER_MAX_BYTES
    _buffer: deque[bytes] = field(default_factory=deque)
    _size: int = 0

    # Alt-screen state
    _in_alt_screen: bool = False
    _normal_snapshot: deque[bytes] | None = None
    _normal_snapshot_size: int = 0

    @property
    def size(self) -> int:
        """Current buffer size in bytes."""
        return self._size

    @property
    def is_empty(self) -> bool:
        """Check if buffer is empty."""
        return self._size == 0

    @property
    def in_alt_screen(self) -> bool:
        """Check if currently in alternate screen mode."""
        return self._in_alt_screen

    def _enter_alt_screen(self) -> None:
        """Handle alt-screen entry: snapshot normal buffer."""
        if self._in_alt_screen:
            return  # Already in alt-screen, ignore nested
        self._in_alt_screen = True
        self._normal_snapshot = self._buffer.copy()
        self._normal_snapshot_size = self._size
        self._clear_buffer()

    def _exit_alt_screen(self) -> None:
        """Handle alt-screen exit: restore normal buffer."""
        if not self._in_alt_screen:
            return  # Not in alt-screen, ignore
        self._in_alt_screen = False
        if self._normal_snapshot is not None:
            self._buffer = self._normal_snapshot
            self._size = self._normal_snapshot_size
            self._normal_snapshot = None
            self._normal_snapshot_size = 0

    def _clear_buffer(self) -> None:
        """Clear the buffer contents only."""
        self._buffer.clear()
        self._size = 0

    def add(self, data: bytes) -> None:
        """Add data to the buffer.

        Handles alt-screen transitions, clear screen detection, and size limits.
        When clear screen is detected, only keep content AFTER the last clear sequence.
        """
        # Check alt-screen transitions FIRST
        for pattern in ALT_SCREEN_EXIT:
            if pattern in data:
                self._exit_alt_screen()
                break
        else:
            for pattern in ALT_SCREEN_ENTER:
                if pattern in data:
                    self._enter_alt_screen()
                    return  # Don't buffer alt-screen enter data

        # Check for clear screen sequence
        if CLEAR_SCREEN_SEQUENCE in data:
            # Clear old buffer
            self.clear()
            # Find the LAST occurrence of clear screen and only keep content after it
            last_clear_pos = data.rfind(CLEAR_SCREEN_SEQUENCE)
            data_after_clear = data[last_clear_pos + len(CLEAR_SCREEN_SEQUENCE) :]
            # Only add if there's meaningful content after clear
            if data_after_clear:
                self._buffer.append(data_after_clear)
                self._size += len(data_after_clear)
            return

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
