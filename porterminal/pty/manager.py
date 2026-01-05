"""Secure PTY manager with security controls."""

import logging
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from porterminal.domain.values import MAX_COLS, MAX_ROWS, MIN_COLS, MIN_ROWS

from .env import build_safe_environment
from .protocol import PTYBackend

if TYPE_CHECKING:
    from ..config import ShellConfig

logger = logging.getLogger(__name__)


class SecurePTYManager:
    """PTY manager with security controls - delegates to platform backend.

    This class provides:
    - Environment variable sanitization
    - Shell path validation
    - Bounds checking for terminal dimensions
    - Unified interface across platforms
    """

    def __init__(
        self,
        backend: PTYBackend,
        shell_config: "ShellConfig",
        cols: int = 120,
        rows: int = 30,
        cwd: str | None = None,
    ) -> None:
        """Initialize the PTY manager.

        Args:
            backend: Platform-specific PTY backend.
            shell_config: Shell configuration (command, args).
            cols: Initial terminal columns (clamped to 40-500).
            rows: Initial terminal rows (clamped to 10-200).
            cwd: Working directory, or None for default.
        """
        self._backend = backend
        self.shell_config = shell_config
        self.cols = max(MIN_COLS, min(cols, MAX_COLS))
        self.rows = max(MIN_ROWS, min(rows, MAX_ROWS))
        self.cwd = cwd
        self._closed = False

    def _build_command(self) -> list[str]:
        """Build the shell command with arguments."""
        cmd = [self.shell_config.command]
        cmd.extend(self.shell_config.args)
        return cmd

    def spawn(self) -> "SecurePTYManager":
        """Spawn the PTY process.

        Returns:
            Self for method chaining.

        Raises:
            FileNotFoundError: If shell command is not found.
        """
        # Verify shell exists
        shell_cmd = self.shell_config.command
        if not shutil.which(shell_cmd) and not Path(shell_cmd).exists():
            raise FileNotFoundError(f"Shell not found: {shell_cmd}")

        # Build command and environment
        cmd = self._build_command()
        env = build_safe_environment()

        # Validate working directory
        cwd = self.cwd
        if cwd:
            cwd_path = Path(cwd)
            if not cwd_path.exists() or not cwd_path.is_dir():
                logger.warning("Invalid cwd %s, using default", cwd)
                cwd = None

        logger.info(
            "Spawning PTY cmd=%s rows=%d cols=%d cwd=%s",
            cmd,
            self.rows,
            self.cols,
            cwd,
        )

        self._backend.spawn(cmd, env, cwd, self.rows, self.cols)
        return self

    def read(self, size: int = 4096) -> bytes:
        """Read from the PTY (non-blocking).

        Args:
            size: Maximum bytes to read.

        Returns:
            Bytes read, or empty bytes if nothing available or closed.
        """
        if self._closed:
            return b""

        try:
            return self._backend.read(size)
        except OSError as e:
            logger.error("PTY read error: %s", e)
            return b""

    def write(self, data: bytes) -> None:
        """Write to the PTY.

        Args:
            data: Bytes to write.
        """
        if self._closed:
            return

        try:
            self._backend.write(data)
        except OSError as e:
            logger.error("PTY write error: %s", e)

    def resize(self, cols: int, rows: int) -> None:
        """Resize the PTY with bounds checking.

        Args:
            cols: New number of columns (clamped to 40-500).
            rows: New number of rows (clamped to 10-200).
        """
        if self._closed:
            return

        cols = max(MIN_COLS, min(cols, MAX_COLS))
        rows = max(MIN_ROWS, min(rows, MAX_ROWS))

        try:
            self._backend.resize(rows, cols)
            self.cols = cols
            self.rows = rows
        except OSError as e:
            logger.error("PTY resize error: %s", e)

    def is_alive(self) -> bool:
        """Check if the PTY process is still alive.

        Returns:
            True if process is running and not closed, False otherwise.
        """
        if self._closed:
            return False
        return self._backend.is_alive()

    def close(self) -> None:
        """Close the PTY and clean up resources."""
        if self._closed:
            return

        self._closed = True
        self._backend.close()
        logger.info("PTY closed")
