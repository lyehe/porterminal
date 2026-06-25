"""Agent connection port - the surface AgentTerminalService drives.

Extends ``ConnectionPort`` (the streaming side used by ``TerminalService``)
with the request/response helpers an MCP agent session needs. Infrastructure's
``AgentSessionConnection`` implements this; typing the service against it keeps
the previously-implicit contract checkable instead of ``Any``.
"""

from typing import Protocol

from .connection_port import ConnectionPort


class AgentConnectionPort(ConnectionPort, Protocol):
    """ConnectionPort plus the agent-facing read/write helpers."""

    @property
    def total_received(self) -> int:
        """Absolute count of output bytes ever received (survives trimming)."""
        ...

    async def push_input(self, data: bytes) -> None:
        """Queue input for the PTY (chunked to the input-size guard)."""
        ...

    def capture_since(self, absolute_offset: int) -> bytes:
        """Raw captured output bytes received since the given absolute offset."""
        ...

    async def wait_for_output(self, timeout: float) -> bool:
        """Wait until new output arrives or timeout. True if signalled."""
        ...

    def screen_lines(self) -> list[str]:
        """Current rendered screen as text lines."""
        ...

    def cursor(self) -> tuple[int, int]:
        """Current cursor position as (row, col)."""
        ...

    def take_error(self) -> str | None:
        """Return and clear the last captured error message, if any."""
        ...
