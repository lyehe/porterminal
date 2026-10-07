"""Output buffer entity for session reconnection."""

import re
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

_CONTROL_SEQUENCES = (*ALT_SCREEN_ENTER, *ALT_SCREEN_EXIT, CLEAR_SCREEN_SEQUENCE)
_CONTROL_PATTERN = re.compile(b"|".join(re.escape(seq) for seq in _CONTROL_SEQUENCES))
_CONTROL_PREFIXES = frozenset(
    seq[:length] for seq in _CONTROL_SEQUENCES for length in range(1, len(seq))
)
_MAX_CONTROL_PREFIX = max(map(len, _CONTROL_PREFIXES))


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
    # Hold only a possible incomplete control sequence, never an arbitrary chunk.
    _pending_control: bytes = b""

    @property
    def size(self) -> int:
        """Current buffer size in bytes."""
        return min(self.max_bytes, self._size + len(self._pending_control))

    @property
    def is_empty(self) -> bool:
        """Check if buffer is empty."""
        return self.size == 0

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
        data = self._pending_control + data
        self._pending_control = b""
        offset = 0
        # Apply controls in stream order, including those split across PTY reads.
        for match in _CONTROL_PATTERN.finditer(data):
            self._append(data[offset : match.start()])
            sequence = match.group()
            if sequence in ALT_SCREEN_ENTER:
                self._enter_alt_screen()
            elif sequence in ALT_SCREEN_EXIT:
                self._exit_alt_screen()
                self._append(sequence)
            else:
                self._clear_buffer()
            offset = match.end()

        tail = data[offset:]
        for length in range(min(len(tail), _MAX_CONTROL_PREFIX), 0, -1):
            if tail[-length:] in _CONTROL_PREFIXES:
                self._pending_control = tail[-length:]
                tail = tail[:-length]
                break
        self._append(tail)

    def _append(self, data: bytes) -> None:
        if data:
            self._buffer.append(data)
            self._size += len(data)
        limit = max(0, self.max_bytes - len(self._pending_control))
        # Retain the most recent bytes even when a single read exceeds the limit.
        while self._size > limit and self._buffer:
            removed = self._buffer.popleft()
            excess = self._size - limit
            if len(removed) > excess:
                self._buffer.appendleft(removed[excess:])
                self._size -= excess
            else:
                self._size -= len(removed)

    def get_all(self) -> bytes:
        """Get all buffered output as single bytes object."""
        data = b"".join(self._buffer) + self._pending_control
        return data[-self.max_bytes :] if self.max_bytes > 0 else b""

    def clear(self) -> None:
        """Clear the buffer."""
        self._clear_buffer()
        self._pending_control = b""
