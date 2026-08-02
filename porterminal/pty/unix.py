"""Unix PTY backend using the pty module."""

import logging
import os
import select
import sys
import time
from importlib import import_module
from typing import Any, cast

logger = logging.getLogger(__name__)

# Unix-only modules are loaded dynamically so importing the package remains safe
# on Windows while this backend can still be checked as part of the full package.
fcntl: Any = None
pty: Any = None
signal: Any = None
struct: Any = None
termios: Any = None
if sys.platform != "win32":
    fcntl = cast(Any, import_module("fcntl"))
    pty = cast(Any, import_module("pty"))
    signal = cast(Any, import_module("signal"))
    struct = cast(Any, import_module("struct"))
    termios = cast(Any, import_module("termios"))

O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
WNOHANG = getattr(os, "WNOHANG", 1)


class UnixPTYBackend:
    """Unix PTY implementation using the pty module."""

    def __init__(self) -> None:
        if sys.platform == "win32":
            raise RuntimeError("UnixPTYBackend is not supported on Windows")
        self._master_fd: int | None = None
        self._pid: int | None = None
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
        """Spawn PTY on Unix using pty module."""
        if self._master_fd is not None:
            raise RuntimeError("PTY already spawned")

        self._rows = rows
        self._cols = cols

        self._pid, self._master_fd = pty.fork()

        if self._pid == 0:
            # Child process
            if cwd:
                os.chdir(cwd)
            os.execvpe(cmd[0], cmd, env)
        else:
            # Parent process - set non-blocking
            flags = fcntl.fcntl(self._master_fd, fcntl.F_GETFL)
            fcntl.fcntl(self._master_fd, fcntl.F_SETFL, flags | O_NONBLOCK)
            # Set initial size
            self._set_winsize(rows, cols)
            logger.debug("Unix PTY spawned pid=%d cmd=%s", self._pid, cmd)

    def _set_winsize(self, rows: int, cols: int) -> None:
        """Set window size on Unix PTY."""
        if self._master_fd is None:
            return
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(self._master_fd, termios.TIOCSWINSZ, winsize)

    def read(self, size: int = 4096) -> bytes:
        """Read from Unix PTY (non-blocking)."""
        if self._master_fd is None:
            return b""

        readable, _, _ = select.select([self._master_fd], [], [], 0)
        if not readable:
            return b""

        try:
            data = os.read(self._master_fd, size)
            if data:
                logger.debug("PTY read bytes=%d", len(data))
            return data
        except OSError:
            return b""

    def write(self, data: bytes) -> None:
        """Write to Unix PTY."""
        if self._master_fd is None:
            return
        logger.debug("PTY write bytes=%d", len(data))
        os.write(self._master_fd, data)

    def resize(self, rows: int, cols: int) -> None:
        """Resize the PTY window."""
        self._set_winsize(rows, cols)
        self._rows = rows
        self._cols = cols
        logger.debug("PTY resize rows=%d cols=%d", rows, cols)

    def is_alive(self) -> bool:
        """Check if the PTY process is still alive."""
        if self._pid is None:
            return False
        try:
            pid, _ = os.waitpid(self._pid, WNOHANG)
            return pid == 0
        except ChildProcessError:
            return False

    def close(self) -> None:
        """Close the PTY and clean up resources."""
        try:
            if self._master_fd is not None:
                os.close(self._master_fd)
                self._master_fd = None

            if self._pid is not None:
                try:
                    # Send SIGTERM for graceful termination
                    os.kill(self._pid, signal.SIGTERM)

                    # Poll with WNOHANG for up to 3 seconds
                    grace_period_ms = 3000
                    poll_interval_ms = 100
                    elapsed = 0

                    while elapsed < grace_period_ms:
                        pid, _ = os.waitpid(self._pid, WNOHANG)
                        if pid != 0:
                            # Process exited gracefully
                            logger.debug("PTY process exited gracefully after SIGTERM")
                            self._pid = None
                            return
                        time.sleep(poll_interval_ms / 1000)
                        elapsed += poll_interval_ms

                    # Process didn't respond to SIGTERM, escalate to SIGKILL
                    logger.warning(
                        "PTY process %d did not respond to SIGTERM, sending SIGKILL",
                        self._pid,
                    )
                    os.kill(self._pid, signal.SIGKILL)
                    os.waitpid(self._pid, 0)  # SIGKILL cannot be ignored

                except (ProcessLookupError, ChildProcessError):
                    # Process already dead
                    pass
                finally:
                    self._pid = None
        except OSError as e:
            logger.error("PTY close error: %s", e)
        finally:
            logger.info("Unix PTY closed")
