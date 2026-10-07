"""Terminal service - terminal I/O coordination."""

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import monotonic
from typing import Any

from porterminal.domain import (
    PTYPort,
    RateLimitConfig,
    Session,
    SessionId,
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

    paused_at: float | None = None
    pending_output: bytearray = field(default_factory=bytearray)
    failed: bool = False
    writer_task: asyncio.Task[None] | None = None
    close_task: asyncio.Task[None] | None = None


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
FLOW_PAUSE_TIMEOUT = 5.0  # seconds - auto-resume if client stops sending ACKs
FLOW_BUFFER_MAX_BYTES = 1_000_000
OUTPUT_SEND_TIMEOUT = 5.0


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
        flow = self._flow_state.pop(connection, None)
        if flow:
            flow.pending_output.clear()
            for task in (flow.writer_task, flow.close_task):
                if task:
                    task.cancel()

        if session_id not in self._session_connections:
            return 0
        self._session_connections[session_id].discard(connection)
        count = len(self._session_connections[session_id])
        if count == 0:
            del self._session_connections[session_id]
        return count

    def start_session(self, session: Session[PTYPort]) -> None:
        """Drain output for the session's lifetime, including when nobody is viewing."""
        session_id = str(session.id)
        existing = self._session_read_tasks.get(session_id)
        if existing and not existing.done():
            return

        self._session_read_tasks[session_id] = asyncio.create_task(
            self._read_pty_broadcast_loop(session, session_id)
        )
        logger.debug("Started broadcast read loop session_id=%s", session_id)

    async def stop_session(self, session_id: SessionId) -> None:
        """Stop PTY reads before the session's handle is closed."""
        key = str(session_id)
        task = self._session_read_tasks.pop(key, None)
        if task and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        delivery_tasks: list[asyncio.Task[None]] = []
        for connection in list(self._session_connections.get(key, set())):
            flow = self._flow_state.get(connection)
            if flow:
                delivery_tasks.extend(
                    task for task in (flow.writer_task, flow.close_task) if task is not None
                )
            self._unregister_connection(key, connection)
        if delivery_tasks:
            await asyncio.gather(*delivery_tasks, return_exceptions=True)
        self._session_locks.pop(key, None)
        logger.debug("Stopped broadcast read loop session_id=%s", session_id)

    async def _close_output_connection(
        self, connection: ConnectionPort, *, code: int, reason: str
    ) -> None:
        with suppress(Exception):
            await asyncio.wait_for(connection.close(code=code, reason=reason), OUTPUT_SEND_TIMEOUT)

    async def _send_connection_output(self, connection: ConnectionPort, data: bytes) -> None:
        """Enqueue without waiting for a viewer's network I/O."""
        flow = self._flow_state.get(connection)
        if flow is None or flow.failed:
            return
        if len(flow.pending_output) + len(data) > FLOW_BUFFER_MAX_BYTES:
            # Bound slow and paused viewers alike. Reconnection replays the session buffer.
            flow.failed = True
            flow.pending_output.clear()
            if flow.writer_task:
                flow.writer_task.cancel()
            flow.close_task = asyncio.create_task(
                self._close_output_connection(
                    connection, code=1013, reason="Output backlog full; reconnect to replay"
                )
            )
            return

        flow.pending_output.extend(data)
        if flow.paused_at is not None:
            if monotonic() - flow.paused_at <= FLOW_PAUSE_TIMEOUT:
                return
            flow.paused_at = None
        if flow.pending_output and (flow.writer_task is None or flow.writer_task.done()):
            flow.writer_task = asyncio.create_task(self._drain_connection_output(connection, flow))

    async def _drain_connection_output(
        self, connection: ConnectionPort, flow: ConnectionFlowState
    ) -> None:
        try:
            while flow.pending_output and self._flow_state.get(connection) is flow:
                if flow.failed or flow.paused_at is not None:
                    return
                payload = bytes(flow.pending_output)
                flow.pending_output.clear()
                try:
                    await asyncio.wait_for(connection.send_output(payload), OUTPUT_SEND_TIMEOUT)
                except Exception as error:
                    flow.failed = True
                    flow.pending_output.clear()
                    logger.debug("Failed to send output to connection: %s", error)
                    await self._close_output_connection(
                        connection, code=1011, reason="Terminal output delivery failed"
                    )
                    return
        finally:
            flow.writer_task = None

    async def _send_to_connections(self, connections: list[ConnectionPort], data: bytes) -> None:
        """Deliver or queue output independently for each viewer, preserving byte order."""
        for connection in connections:
            await self._send_connection_output(connection, data)

    async def _broadcast_output(self, session_id: str, data: bytes) -> None:
        """Broadcast PTY output to all connections for a session.

        Note: This is only used for error/status messages where the race
        condition doesn't matter. For PTY data, use _send_to_connections
        with a lock-protected snapshot.
        """
        await self._send_to_connections(
            list(self._session_connections.get(session_id, set())), data
        )

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
        rate_limit_config: RateLimitConfig | None = None,
    ) -> None:
        """Handle terminal session I/O with multi-client support.

        Multiple clients can connect to the same session simultaneously.
        The PTY reader belongs to the session and keeps draining after clients disconnect.

        Args:
            session: Terminal session to handle.
            connection: Network connection to client.
            skip_buffer: Whether to skip sending buffered output.
            rate_limit_config: Per-connection override of the input rate limit.
                Agent connections pass an effectively-unlimited config because
                the default limiter (1 KB/s sustained) exists to throttle an
                unauthenticated human client and would silently drop a trusted
                agent's bulk input.
        """
        session_id = str(session.id)
        clock = AsyncioClock()
        rate_limiter = TokenBucketRateLimiter(rate_limit_config or self._rate_limit_config, clock)
        lock = self._get_session_lock(session_id)

        # Register and snapshot together so replay cannot duplicate a live broadcast.
        # Network I/O happens after releasing the session lock.
        async with lock:
            connection_count = self._register_connection(session_id, connection)
            logger.info(
                "Client connected session_id=%s connection_count=%d",
                session_id,
                connection_count,
            )

            # Standalone callers may not have started the reader at session creation.
            if connection_count == 1:
                self.start_session(session)

            # Snapshot buffer while under lock (ensures consistency with broadcast)
            # Note: session_info is sent by the caller (app.py) to include tab_id
            if not skip_buffer and not session.output_buffer.is_empty:
                # Queue replay first, before the reader can enqueue any live output.
                await self._send_connection_output(connection, session.get_buffered_output())

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
            flow = self._flow_state.get(connection)
            delivery_tasks = (
                [task for task in (flow.writer_task, flow.close_task) if task is not None]
                if flow
                else []
            )
            remaining = self._unregister_connection(session_id, connection)
            if delivery_tasks:
                await asyncio.gather(*delivery_tasks, return_exceptions=True)

            logger.info(
                "Client disconnected session_id=%s remaining_connections=%d",
                session_id,
                remaining,
            )

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

        while session.pty_handle.is_alive():
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
        if not session.pty_handle.is_alive():
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

        if not data:
            return

        # Terminal query replies are input too: shells such as Fish wait for
        # device attributes before accepting commands.
        if rate_limiter.try_acquire(len(data)):
            session.pty_handle.write(data)
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
                flow.paused_at = monotonic()
                # Send confirmation so client knows pause was received
                await connection.send_message({"type": "pause_ack"})
                logger.debug("Connection paused (client overwhelmed) session_id=%s", session.id)
        elif msg_type == "ack":
            # Client caught up - resume sending data
            flow = self._flow_state.get(connection)
            if flow and flow.paused_at is not None:
                flow.paused_at = None
                await self._send_connection_output(connection, b"")
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
