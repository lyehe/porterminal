"""Shell detection for available shells on the system."""

import shutil
import sys
from pathlib import Path

from porterminal.domain import ShellCommand


class ShellDetector:
    """Detect available shells on the current platform."""

    def detect_shells(self) -> list[ShellCommand]:
        """Auto-detect available shells.

        Returns:
            List of detected shell configurations.
        """
        candidates = self._get_platform_candidates()
        shells = []

        for name, shell_id, command, args in candidates:
            shell_path = shutil.which(command)
            if shell_path or Path(command).exists():
                shells.append(
                    ShellCommand(
                        id=shell_id,
                        name=name,
                        command=shell_path or command,
                        args=tuple(args),
                    )
                )

        return shells

    def get_default_shell_id(self) -> str:
        """Get the default shell ID for current platform."""
        if sys.platform == "win32":
            return self._get_windows_default()
        elif sys.platform == "darwin":
            return self._get_macos_default()
        return self._get_linux_default()

    def _get_platform_candidates(self) -> list[tuple[str, str, str, list[str]]]:
        """Get shell candidates for current platform.

        Returns:
            List of (name, id, command, args) tuples.
        """
        if sys.platform == "win32":
            return [
                ("PS 7", "pwsh", "pwsh.exe", ["-NoLogo"]),
                ("PS", "powershell", "powershell.exe", ["-NoLogo"]),
                ("CMD", "cmd", "cmd.exe", []),
                ("WSL", "wsl", "wsl.exe", []),
                ("Git Bash", "gitbash", r"C:\Program Files\Git\bin\bash.exe", ["--login"]),
            ]
        return [
            ("Bash", "bash", "bash", ["--login"]),
            ("Zsh", "zsh", "zsh", ["--login"]),
            ("Fish", "fish", "fish", []),
            ("Sh", "sh", "sh", []),
        ]

    def _get_windows_default(self) -> str:
        """Get default shell ID for Windows."""
        if shutil.which("pwsh.exe"):
            return "pwsh"
        if shutil.which("powershell.exe"):
            return "powershell"
        return "cmd"

    def _get_macos_default(self) -> str:
        """Get default shell ID for macOS."""
        if shutil.which("zsh"):
            return "zsh"
        return "bash"

    def _get_linux_default(self) -> str:
        """Get default shell ID for Linux."""
        if shutil.which("bash"):
            return "bash"
        if shutil.which("zsh"):
            return "zsh"
        return "sh"
