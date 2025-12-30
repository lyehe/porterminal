"""Terminal service - terminal I/O coordination."""

import asyncio
import logging
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

# Constants
HEARTBEAT_INTERVAL = 30  # seconds
HEARTBEAT_TIMEOUT = 300  # 5 minutes
PTY_READ_INTERVAL = 0.008  # ~120Hz
MAX_INPUT_SIZE = 4096


class AsyncioClock:
    """Clock implementation using asyncio event loop time."""

    def now(self) -> float:
        return asyncio.get_running_loop().time()


class TerminalService:
    """Service for handling terminal I/O.

    Coordinates PTY reads, WebSocket writes, and message handling.
    """

    def __init__(
        self,
        rate_limit_config: RateLimitConfig | None = None,
        max_input_size: int = MAX_INPUT_SIZE,
    ) -> None:
        self._rate_limit_config = rate_limit_config or RateLimitConfig()
        self._max_input_size = max_input_size

    async def handle_session(
        self,
        session: Session[PTYPort],
        connection: ConnectionPort,
        skip_buffer: bool = False,
    ) -> None:
        """Handle terminal session I/O.

        Args:
            session: Terminal session to handle.
            connection: Network connection to client.
            skip_buffer: Whether to skip sending buffered output.
        """
        clock = AsyncioClock()
        rate_limiter = TokenBucketRateLimiter(self._rate_limit_config, clock)

        # Send session info
        await connection.send_message(
            {
                "type": "session_info",
                "session_id": str(session.id),
                "shell": session.shell_id,
            }
        )

        # Replay buffered output
        if not skip_buffer and not session.output_buffer.is_empty:
            buffered = session.get_buffered_output()
            session.clear_buffer()  # Clear after getting output
            if buffered:
                await connection.send_output(buffered)

        # Start tasks
        read_task = asyncio.create_task(self._read_pty_loop(session, connection))
        heartbeat_task = asyncio.create_task(self._heartbeat_loop(connection))

        try:
            await self._handle_input_loop(session, connection, rate_limiter)
        finally:
            read_task.cancel()
            heartbeat_task.cancel()
            try:
                await read_task
            except asyncio.CancelledError:
                pass
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

    async def _read_pty_loop(
        self,
        session: Session[PTYPort],
        connection: ConnectionPort,
    ) -> None:
        """Read from PTY and send to client."""
        # Check if PTY is alive at start
        if not session.pty_handle.is_alive():
            logger.error("PTY not alive at start session_id=%s", session.id)
            await connection.send_output(b"\r\n[PTY failed to start]\r\n")
            return

        while connection.is_connected() and session.pty_handle.is_alive():
            try:
                data = session.pty_handle.read(4096)
                if data:
                    session.add_output(data)
                    await connection.send_output(data)
                    session.touch(datetime.now(UTC))
            except Exception as e:
                logger.error("PTY read error session_id=%s: %s", session.id, e)
                await connection.send_output(f"\r\n[PTY error: {e}]\r\n".encode())
                break

            await asyncio.sleep(PTY_READ_INTERVAL)

        # Notify client if PTY died
        if connection.is_connected() and not session.pty_handle.is_alive():
            await connection.send_output(b"\r\n[Shell exited]\r\n")

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
                await self._handle_json_message(session, message, rate_limiter, connection)

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
        rate_limiter: TokenBucketRateLimiter,
        connection: ConnectionPort,
    ) -> None:
        """Handle JSON control message."""
        msg_type = message.get("type")

        if msg_type == "resize":
            await self._handle_resize(session, message)
        elif msg_type == "input":
            await self._handle_json_input(session, message, rate_limiter, connection)
        elif msg_type == "ping":
            await connection.send_message({"type": "pong"})
            session.touch(datetime.now(UTC))
        elif msg_type == "pong":
            session.touch(datetime.now(UTC))
        else:
            logger.warning("Unknown message type session_id=%s type=%s", session.id, msg_type)

    async def _handle_resize(
        self,
        session: Session[PTYPort],
        message: dict[str, Any],
    ) -> None:
        """Handle terminal resize message."""
        cols = int(message.get("cols", 120))
        rows = int(message.get("rows", 30))

        new_dims = TerminalDimensions.clamped(cols, rows)

        # Skip if same as current
        if session.dimensions == new_dims:
            return

        session.update_dimensions(new_dims)
        session.pty_handle.resize(new_dims)
        session.touch(datetime.now(UTC))

        logger.info(
            "Terminal resized session_id=%s cols=%d rows=%d",
            session.id,
            new_dims.cols,
            new_dims.rows,
        )

    async def _handle_json_input(
        self,
        session: Session[PTYPort],
        message: dict[str, Any],
        rate_limiter: TokenBucketRateLimiter,
        connection: ConnectionPort,
    ) -> None:
        """Handle JSON-encoded terminal input."""
        data = message.get("data", "")

        if len(data) > self._max_input_size:
            await connection.send_message(
                {
                    "type": "error",
                    "message": "Input too large",
                }
            )
            return

        if data:
            input_bytes = data.encode("utf-8")
            if rate_limiter.try_acquire(len(input_bytes)):
                session.pty_handle.write(input_bytes)
                session.touch(datetime.now(UTC))
            else:
                await connection.send_message(
                    {
                        "type": "error",
                        "message": "Rate limit exceeded",
                    }
                )
