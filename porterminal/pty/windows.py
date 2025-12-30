"""Windows PTY backend using pywinpty."""

import logging
import select
import time
from typing import Any

logger = logging.getLogger(__name__)

# Import pywinpty - only available on Windows
try:
    from winpty import PtyProcess as WinPtyProcess

    HAS_WINPTY = True
except ImportError:
    WinPtyProcess = None  # type: ignore[misc, assignment]
    HAS_WINPTY = False


class WindowsPTYBackend:
    """Windows PTY implementation using pywinpty."""

    def __init__(self) -> None:
        if not HAS_WINPTY:
            raise RuntimeError("pywinpty is not installed")
        self._pty: Any | None = None
        self._rows: int = 30
        self._cols: int = 120

    @property
    def rows(self) -> int:
        """Current number of rows."""
        return self._rows

    @property
    def cols(self) -> int:
        """Current number of columns."""
        return self._cols

    def spawn(
        self,
        cmd: list[str],
        env: dict[str, str],
        cwd: str | None,
        rows: int,
        cols: int,
    ) -> None:
        """Spawn PTY on Windows using pywinpty."""
        if self._pty is not None:
            raise RuntimeError("PTY already spawned")

        self._rows = rows
        self._cols = cols

        self._pty = WinPtyProcess.spawn(
            cmd,
            dimensions=(rows, cols),
            env=env,
            cwd=cwd,
        )
        logger.debug("Windows PTY spawned cmd=%s", cmd)

    def read(self, size: int = 4096) -> bytes:
        """Read from Windows PTY (non-blocking)."""
        if self._pty is None:
            return b""

        # Try socket-based read first (faster)
        sock = getattr(self._pty, "fileobj", None)
        if sock is not None:
            readable, _, _ = select.select([sock], [], [], 0)
            if not readable:
                return b""
            data = sock.recv(size)
            # Filter out pywinpty noise
            if not data or data == b"0011Ignore":
                return b""
            logger.debug("PTY read bytes=%d", len(data))
            return data

        # Fallback to blocking read
        data = self._pty.read(size)
        data_bytes = data.encode("utf-8") if isinstance(data, str) else data
        if data_bytes:
            logger.debug("PTY read bytes=%d", len(data_bytes))
        return data_bytes

    def write(self, data: bytes) -> None:
        """Write to Windows PTY."""
        if self._pty is None:
            return
        text = data.decode("utf-8", errors="replace")
        logger.debug("PTY write bytes=%d", len(data))
        self._pty.write(text)

    def resize(self, rows: int, cols: int) -> None:
        """Resize the PTY window."""
        if self._pty is None:
            return
        self._pty.setwinsize(rows, cols)
        self._rows = rows
        self._cols = cols
        logger.debug("PTY resize rows=%d cols=%d", rows, cols)

    def is_alive(self) -> bool:
        """Check if the PTY process is still alive."""
        return self._pty is not None and self._pty.isalive()

    def close(self) -> None:
        """Close the PTY with grace period before force kill."""
        if self._pty is None:
            return

        try:
            if self._pty.isalive():
                # Try graceful termination first
                self._pty.terminate(force=False)
                # Wait up to 3 seconds for process to exit
                for _ in range(30):
                    if not self._pty.isalive():
                        break
                    time.sleep(0.1)
                # Force kill if still alive
                if self._pty.isalive():
                    logger.debug("PTY did not exit gracefully, force killing")
                    self._pty.terminate(force=True)
        except OSError as e:
            logger.error("PTY close error: %s", e)
        finally:
            self._pty = None
            logger.info("Windows PTY closed")
