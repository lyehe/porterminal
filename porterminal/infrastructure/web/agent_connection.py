"""Agent session connection - bridges MCP request/response tools to the
streaming ConnectionPort model used by TerminalService.

An ``AgentSessionConnection`` looks like any other terminal client to
``TerminalService`` (it implements the ``ConnectionPort`` protocol), but
instead of a WebSocket it:

- feeds PTY output bytes into a ``pyte`` screen (for ``read_screen``) and a
  bounded raw capture buffer (for ``run_command`` marker scanning),
- receives input from an internal queue that the MCP tools push onto,
- captures error/control messages so tools can surface them rather than
  silently dropping them.

Because the agent is just another connection on the session, the existing
multi-client broadcast means a human watching the same session on their
phone co-views and can take over for free.
"""

import asyncio
import logging

import pyte

logger = logging.getLogger(__name__)

# Cap the raw capture buffer; commands are short, so this only trims between
# commands. We track how many bytes were dropped so absolute offsets taken by
# run_command stay valid.
_CAPTURE_CAP = 1_048_576  # 1 MiB

# Max bytes per PTY write - mirrors TerminalService.MAX_INPUT_SIZE so the
# input-size guard never rejects a large command/paste from the agent.
_MAX_WRITE = 4096


class AgentSessionConnection:
    """A non-WebSocket ConnectionPort driven by MCP tool calls."""

    def __init__(self, cols: int, rows: int) -> None:
        self._screen = pyte.Screen(cols, rows)
        self._stream = pyte.ByteStream(self._screen)

        self._capture = bytearray()
        self._dropped = 0  # bytes trimmed from the front of _capture

        self._input: asyncio.Queue[bytes] = asyncio.Queue()
        self._output_event = asyncio.Event()
        self._connected = True
        self._last_error: str | None = None

    # ------------------------------------------------------------------
    # ConnectionPort protocol
    # ------------------------------------------------------------------

    async def send_output(self, data: bytes) -> None:
        """Receive PTY output: render into pyte + append to capture."""
        try:
            self._stream.feed(data)
        except Exception:
            # pyte should never raise on valid terminal output, but a rendering
            # error must not kill the read loop / lose the raw capture.
            logger.debug("pyte feed error (ignored; raw capture kept)", exc_info=True)
        self._capture += data
        if len(self._capture) > _CAPTURE_CAP:
            trim = len(self._capture) - _CAPTURE_CAP
            self._dropped += trim
            del self._capture[:trim]
        self._output_event.set()

    async def send_message(self, message: dict) -> None:
        """Capture errors so tools can report them; ignore heartbeat/flow msgs."""
        if message.get("type") == "error":
            self._last_error = str(message.get("message", "error"))

    async def receive(self) -> bytes:
        """Return queued agent input for the PTY write loop."""
        return await self._input.get()

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self._connected = False
        # Unblock a pending receive() so TerminalService's input loop can notice
        # is_connected() is now False and exit.
        self._input.put_nowait(b"")

    def is_connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------
    # Agent-facing helpers (used by AgentTerminalService)
    # ------------------------------------------------------------------

    async def push_input(self, data: bytes) -> None:
        """Queue input for the PTY, chunked to stay under the size guard."""
        for i in range(0, len(data), _MAX_WRITE):
            await self._input.put(data[i : i + _MAX_WRITE])

    @property
    def total_received(self) -> int:
        """Absolute count of output bytes ever received (survives trimming)."""
        return self._dropped + len(self._capture)

    def capture_since(self, absolute_offset: int) -> bytes:
        """Raw captured bytes received since the given absolute offset."""
        start = max(0, absolute_offset - self._dropped)
        return bytes(self._capture[start:])

    async def wait_for_output(self, timeout: float) -> bool:
        """Wait until new output arrives or timeout. Returns True if signalled."""
        self._output_event.clear()
        try:
            await asyncio.wait_for(self._output_event.wait(), timeout)
            return True
        except TimeoutError:
            return False

    def screen_lines(self) -> list[str]:
        """Current rendered screen as a list of text lines."""
        return list(self._screen.display)

    def cursor(self) -> tuple[int, int]:
        """Current cursor position as (row, col)."""
        return (self._screen.cursor.y, self._screen.cursor.x)

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def take_error(self) -> str | None:
        err, self._last_error = self._last_error, None
        return err
