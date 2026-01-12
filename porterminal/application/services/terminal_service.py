"""Terminal service - terminal I/O coordination."""

import asyncio
import logging
import re
import time
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from porterminal.domain import (
    PTYPort,
    RateLimitConfig,
    Session,
    TerminalDimensions,
    TokenBucketRateLimiter,
)

from ..ports.connection_port import ConnectionPort

logger = logging.getLogger(__name__)


@dataclass
class ConnectionFlowState:
    """Per-connection flow control state.

    Implements xterm.js recommended watermark-based flow control.
    When client sends 'pause', we stop sending to that connection.
    When client sends 'ack', we resume sending.
    """

    paused: bool = False
    pause_time: float | None = None


# Terminal response sequences that should NOT be written to PTY.
# These are responses from the terminal emulator to queries from applications.
# If written to PTY, they get echoed back and displayed as garbage.
#
# Patterns:
#   \x1b[?...c  - Device Attributes (DA) response
#   \x1b[...R   - Cursor Position Report (CPR) response
TERMINAL_RESPONSE_PATTERN = re.compile(rb"\x1b\[\?[\d;]*c|\x1b\[[\d;]*R")

# Constants
HEARTBEAT_INTERVAL = 30  # seconds
HEARTBEAT_TIMEOUT = 300  # 5 minutes

# Adaptive PTY read interval: fast when data flowing, slow when idle
PTY_READ_INTERVAL_MIN = 0.001  # 1ms when data is flowing (high throughput)
PTY_READ_INTERVAL_MAX = 0.008  # 8ms when idle (save CPU)
PTY_READ_BURST_THRESHOLD = 5  # Consecutive reads with data before going fast

# Tiered batch intervals: faster for interactive, slower for bulk
OUTPUT_BATCH_INTERVAL_INTERACTIVE = 0.004  # 4ms for small data (<256 bytes)
OUTPUT_BATCH_INTERVAL_BULK = 0.016  # 16ms for larger data
OUTPUT_BATCH_SIZE_THRESHOLD = 256  # Bytes - threshold for interactive vs bulk
OUTPUT_BATCH_MAX_SIZE = 16384  # Flush if batch exceeds 16KB
INTERACTIVE_THRESHOLD = 64  # Bytes - flush immediately for very small data
MAX_INPUT_SIZE = 4096
FLOW_PAUSE_TIMEOUT = 5.0  # seconds - auto-resume if client stops sending ACKs (was 15s)


class AsyncioClock:
    """Clock implementation using asyncio event loop time."""

    def now(self) -> float:
        return asyncio.get_running_loop().time()


class TerminalService:
    """Service for handling terminal I/O.

    Coordinates PTY reads, WebSocket writes, and message handling.
    Supports multiple clients connected to the same session.
    """

    def __init__(
        self,
        rate_limit_config: RateLimitConfig | None = None,
        max_input_size: int = MAX_INPUT_SIZE,
    ) -> None:
        self._rate_limit_config = rate_limit_config or RateLimitConfig()
        self._max_input_size = max_input_size

        # Multi-client support: track connections and read loops per session
        self._session_connections: dict[str, set[ConnectionPort]] = {}
        self._session_read_tasks: dict[str, asyncio.Task[None]] = {}
        # Per-session locks to prevent race between buffer replay and broadcast
        self._session_locks: dict[str, asyncio.Lock] = {}
        # Per-connection flow control state (watermark-based backpressure)
        self._flow_state: dict[ConnectionPort, ConnectionFlowState] = {}

    # -------------------------------------------------------------------------
    # Multi-client connection tracking
    # -------------------------------------------------------------------------

    def _get_session_lock(self, session_id: str) -> asyncio.Lock:
        """Get or create a lock for a session."""
        return self._session_locks.setdefault(session_id, asyncio.Lock())

    def _cleanup_session_lock(self, session_id: str) -> None:
        """Remove session lock when no longer needed."""
        self._session_locks.pop(session_id, None)

    def _register_connection(self, session_id: str, connection: ConnectionPort) -> int:
        """Register a connection for a session. Returns connection count."""
        connections = self._session_connections.setdefault(session_id, set())
        connections.add(connection)
        # Initialize flow control state for this connection
        self._flow_state[connection] = ConnectionFlowState()
        return len(connections)

    def _unregister_connection(self, session_id: str, connection: ConnectionPort) -> int:
        """Unregister a connection. Returns remaining count."""
        # Clean up flow control state
        self._flow_state.pop(connection, None)

        if session_id not in self._session_connections:
            return 0
        self._session_connections[session_id].discard(connection)
        count = len(self._session_connections[session_id])
        if count == 0:
            del self._session_connections[session_id]
        return count

    async def _send_to_connections(self, connections: list[ConnectionPort], data: bytes) -> None:
        """Send data to connections, respecting flow control.

        Skips paused connections (client overwhelmed) but auto-resumes
        after FLOW_PAUSE_TIMEOUT to prevent permanent pause from dead clients.
        """
        current_time = time.time()
        for conn in connections:
            flow = self._flow_state.get(conn)
            if flow and flow.paused:
                # Check timeout - auto-resume if client stopped responding
                if flow.pause_time and (current_time - flow.pause_time) > FLOW_PAUSE_TIMEOUT:
                    flow.paused = False
                    flow.pause_time = None
                    logger.debug("Auto-resumed paused connection after timeout")
                else:
                    continue  # Skip paused connection

            try:
                await conn.send_output(data)
            except Exception as e:
                logger.debug("Failed to send output to connection: %s", e)

    async def _broadcast_output(self, session_id: str, data: bytes) -> None:
        """Broadcast PTY output to all connections for a session.

        Note: This is only used for error/status messages where the race
        condition doesn't matter. For PTY data, use _send_to_connections
        with a lock-protected snapshot.
        """
        connections = self._session_connections.get(session_id, set())
        dead: list[ConnectionPort] = []
        for conn in list(connections):  # Copy to avoid mutation during iteration
            try:
                await conn.send_output(data)
            except Exception:
                dead.append(conn)
        for conn in dead:
            connections.discard(conn)

    async def _broadcast_message(self, session_id: str, message: dict[str, Any]) -> None:
        """Broadcast JSON message to all connections for a session."""
        connections = self._session_connections.get(session_id, set())
        dead: list[ConnectionPort] = []
        for conn in list(connections):
            try:
                await conn.send_message(message)
            except Exception:
                dead.append(conn)
        for conn in dead:
            connections.discard(conn)

    async def handle_session(
        self,
        session: Session[PTYPort],
        connection: ConnectionPort,
        skip_buffer: bool = False,
    ) -> None:
        """Handle terminal session I/O with multi-client support.

        Multiple clients can connect to the same session simultaneously.
        The first client starts the PTY read loop; the last client stops it.

        Args:
            session: Terminal session to handle.
            connection: Network connection to client.
            skip_buffer: Whether to skip sending buffered output.
        """
        session_id = str(session.id)
        clock = AsyncioClock()
        rate_limiter = TokenBucketRateLimiter(self._rate_limit_config, clock)
        lock = self._get_session_lock(session_id)

        # Register atomically to prevent race with broadcast.
        # Without this lock, a new client could register between add_output and
        # broadcast, receiving the same data twice (once from buffer, once broadcast).
        #
        # Buffer snapshot and read loop start are also under lock to ensure:
        # - Buffer is captured before any new data arrives
        # - Only one read loop starts per session (prevents duplicate PTY reads)
        # - I/O (send_output) happens OUTSIDE lock to avoid blocking other clients
        buffered = None
        async with lock:
            connection_count = self._register_connection(session_id, connection)
            is_first_client = connection_count == 1

            logger.info(
                "Client connected session_id=%s connection_count=%d",
                session_id,
                connection_count,
            )

            # First client starts the shared PTY read loop (under lock to prevent duplicates)
            if is_first_client:
                self._start_broadcast_read_loop(session, session_id)

            # Snapshot buffer while under lock (ensures consistency with broadcast)
            # Note: session_info is sent by the caller (app.py) to include tab_id
            if not skip_buffer and not session.output_buffer.is_empty:
                buffered = session.get_buffered_output()

        # Replay buffer OUTSIDE lock to avoid blocking other clients during I/O
        if buffered:
            await connection.send_output(buffered)

        try:
            # Start heartbeat for this connection
            heartbeat_task = asyncio.create_task(self._heartbeat_loop(connection))

            try:
                await self._handle_input_loop(session, connection, rate_limiter)
            finally:
                heartbeat_task.cancel()
                with suppress(asyncio.CancelledError):
                    await heartbeat_task

        finally:
            # Unregister this connection
            remaining = self._unregister_connection(session_id, connection)

            logger.info(
                "Client disconnected session_id=%s remaining_connections=%d",
                session_id,
                remaining,
            )

            # Last client: stop the read loop and cleanup lock
            if remaining == 0:
                await self._stop_broadcast_read_loop(session_id)
                self._cleanup_session_lock(session_id)

    def _start_broadcast_read_loop(
        self,
        session: Session[PTYPort],
        session_id: str,
    ) -> None:
        """Start the PTY read loop that broadcasts to all clients."""
        if session_id in self._session_read_tasks:
            return  # Already running

        task = asyncio.create_task(self._read_pty_broadcast_loop(session, session_id))
        self._session_read_tasks[session_id] = task
        logger.debug("Started broadcast read loop session_id=%s", session_id)

    async def _stop_broadcast_read_loop(self, session_id: str) -> None:
        """Stop the PTY read loop for a session."""
        task = self._session_read_tasks.pop(session_id, None)
        if task and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        logger.debug("Stopped broadcast read loop session_id=%s", session_id)

    async def _read_pty_broadcast_loop(
        self,
        session: Session[PTYPort],
        session_id: str,
    ) -> None:
        """Read from PTY and broadcast to all connected clients.

        Single loop per session, regardless of client count.

        Batching strategy:
        - Small data (<64 bytes): flush immediately for interactive responsiveness
        - Large data: batch for ~16ms to reduce WebSocket message frequency
        - Flush if batch exceeds 16KB to prevent memory buildup

        Thread safety:
        - Uses session lock to prevent race between add_output/broadcast and
          new client registration/buffer replay. Lock is held briefly during
          buffer update and connection snapshot, not during actual I/O.
        """
        # Check if PTY is alive at start
        if not session.pty_handle.is_alive():
            logger.error("PTY not alive at start session_id=%s", session.id)
            await self._broadcast_output(session_id, b"\r\n[PTY failed to start]\r\n")
            return

        lock = self._get_session_lock(session_id)
        batch_buffer: list[bytes] = []
        batch_size = 0
        last_flush_time = asyncio.get_running_loop().time()
        consecutive_data_reads = 0  # Track consecutive reads with data for adaptive sleep

        async def flush_batch() -> None:
            """Flush batched data with lock protection."""
            nonlocal batch_buffer, batch_size, last_flush_time
            if not batch_buffer:
                return

            combined = b"".join(batch_buffer)
            batch_buffer = []
            batch_size = 0
            last_flush_time = asyncio.get_running_loop().time()

            # Acquire lock, add to buffer, snapshot connections, release lock
            async with lock:
                session.add_output(combined)
                connections = list(self._session_connections.get(session_id, set()))

            # Broadcast outside lock (I/O can be slow)
            await self._send_to_connections(connections, combined)

        def has_connections() -> bool:
            return (
                session_id in self._session_connections
                and len(self._session_connections[session_id]) > 0
            )

        while has_connections() and session.pty_handle.is_alive():
            try:
                data = session.pty_handle.read(4096)
                if data:
                    session.touch(datetime.now(UTC))
                    # Track consecutive reads with data for adaptive sleep
                    consecutive_data_reads = min(
                        consecutive_data_reads + 1, PTY_READ_BURST_THRESHOLD
                    )

                    # Small data (interactive): flush immediately for responsiveness
                    if len(data) < INTERACTIVE_THRESHOLD and not batch_buffer:
                        # Acquire lock, add to buffer, snapshot connections
                        async with lock:
                            session.add_output(data)
                            connections = list(self._session_connections.get(session_id, set()))
                        # Broadcast outside lock
                        await self._send_to_connections(connections, data)
                    else:
                        # Batch larger data
                        batch_buffer.append(data)
                        batch_size += len(data)

                        # Flush if batch is large enough
                        if batch_size >= OUTPUT_BATCH_MAX_SIZE:
                            await flush_batch()
                else:
                    # No data - reset burst counter
                    consecutive_data_reads = 0

            except Exception as e:
                logger.error("PTY read error session_id=%s: %s", session.id, e)
                await flush_batch()  # Flush any pending data
                await self._broadcast_output(session_id, f"\r\n[PTY error: {e}]\r\n".encode())
                break

            # Tiered batch interval: faster for small batches, slower for large
            batch_interval = (
                OUTPUT_BATCH_INTERVAL_INTERACTIVE
                if batch_size < OUTPUT_BATCH_SIZE_THRESHOLD
                else OUTPUT_BATCH_INTERVAL_BULK
            )

            # Check if we should flush based on time
            current_time = asyncio.get_running_loop().time()
            if batch_buffer and (current_time - last_flush_time) >= batch_interval:
                await flush_batch()

            # Adaptive sleep: fast when data flowing, slow when idle
            sleep_time = (
                PTY_READ_INTERVAL_MIN
                if consecutive_data_reads >= PTY_READ_BURST_THRESHOLD
                else PTY_READ_INTERVAL_MAX
            )
            await asyncio.sleep(sleep_time)

        # Flush any remaining data
        await flush_batch()

        # Notify all clients if PTY died
        if has_connections() and not session.pty_handle.is_alive():
            await self._broadcast_output(session_id, b"\r\n[Shell exited]\r\n")

    async def _heartbeat_loop(self, connection: ConnectionPort) -> None:
        """Send periodic heartbeat pings."""
        while connection.is_connected():
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            try:
                await connection.send_message({"type": "ping"})
            except Exception:
                break

    async def _handle_input_loop(
        self,
        session: Session[PTYPort],
        connection: ConnectionPort,
        rate_limiter: TokenBucketRateLimiter,
    ) -> None:
        """Handle input from client."""
        while connection.is_connected():
            try:
                message = await connection.receive()
            except Exception:
                break

            if isinstance(message, bytes):
                await self._handle_binary_input(session, message, rate_limiter, connection)
            elif isinstance(message, dict):
                await self._handle_json_message(session, message, connection)

    async def _handle_binary_input(
        self,
        session: Session[PTYPort],
        data: bytes,
        rate_limiter: TokenBucketRateLimiter,
        connection: ConnectionPort,
    ) -> None:
        """Handle binary terminal input."""
        if len(data) > self._max_input_size:
            await connection.send_message(
                {
                    "type": "error",
                    "message": "Input too large",
                }
            )
            return

        # Filter terminal response sequences before writing to PTY.
        # xterm.js generates these in response to DA/CPR queries.
        # If written back to PTY, they get echoed and displayed as garbage.
        filtered = TERMINAL_RESPONSE_PATTERN.sub(b"", data)
        if not filtered:
            return

        if rate_limiter.try_acquire(len(filtered)):
            session.pty_handle.write(filtered)
            session.touch(datetime.now(UTC))
        else:
            await connection.send_message(
                {
                    "type": "error",
                    "message": "Rate limit exceeded",
                }
            )
            logger.warning("Rate limit exceeded session_id=%s", session.id)

    async def _handle_json_message(
        self,
        session: Session[PTYPort],
        message: dict[str, Any],
        connection: ConnectionPort,
    ) -> None:
        """Handle JSON control message."""
        msg_type = message.get("type")

        if msg_type == "resize":
            await self._handle_resize(session, message, connection)
        elif msg_type == "ping":
            await connection.send_message({"type": "pong"})
            session.touch(datetime.now(UTC))
        elif msg_type == "pong":
            session.touch(datetime.now(UTC))
        elif msg_type == "pause":
            # Client is overwhelmed - stop sending data to this connection
            flow = self._flow_state.get(connection)
            if flow:
                flow.paused = True
                flow.pause_time = time.time()
                # Send confirmation so client knows pause was received
                await connection.send_message({"type": "pause_ack"})
                logger.debug("Connection paused (client overwhelmed) session_id=%s", session.id)
        elif msg_type == "ack":
            # Client caught up - resume sending data
            flow = self._flow_state.get(connection)
            if flow and flow.paused:
                flow.paused = False
                flow.pause_time = None
                logger.debug("Connection resumed (client caught up) session_id=%s", session.id)
        else:
            logger.warning("Unknown message type session_id=%s type=%s", session.id, msg_type)

    async def _handle_resize(
        self,
        session: Session[PTYPort],
        message: dict[str, Any],
        connection: ConnectionPort,
    ) -> None:
        """Handle terminal resize message.

        Multi-client strategy:
        - When multiple clients share a session, PTY dimensions are locked
        - Only the first client (or when all clients agree) can resize
        - New clients receive current dimensions and must adapt locally
        - This prevents rendering artifacts from dimension mismatches
        """
        session_id = str(session.id)
        cols = int(message.get("cols", 120))
        rows = int(message.get("rows", 30))

        new_dims = TerminalDimensions.clamped(cols, rows)

        # Skip if same as current
        if session.dimensions == new_dims:
            return

        # Check if multiple clients are connected
        connections = self._session_connections.get(session_id, set())
        if len(connections) > 1:
            # Multiple clients: reject resize, tell client to use current dimensions
            logger.info(
                "Resize rejected (multi-client) session_id=%s requested=%dx%d current=%dx%d",
                session.id,
                new_dims.cols,
                new_dims.rows,
                session.dimensions.cols,
                session.dimensions.rows,
            )
            # Send current dimensions back so client can adapt
            await connection.send_message(
                {
                    "type": "resize_sync",
                    "cols": session.dimensions.cols,
                    "rows": session.dimensions.rows,
                }
            )
            return

        # Single client: allow resize
        session.update_dimensions(new_dims)
        session.pty_handle.resize(new_dims)
        session.touch(datetime.now(UTC))

        logger.info(
            "Terminal resized session_id=%s cols=%d rows=%d",
            session.id,
            new_dims.cols,
            new_dims.rows,
        )
