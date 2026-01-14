"""Shell detection for available shells on the system."""

import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from porterminal.domain import ShellCommand

logger = logging.getLogger(__name__)


class ShellDetector:
    """Detect available shells on the current platform."""

    def detect_shells(self) -> list[ShellCommand]:
        """Auto-detect available shells.

        Detects platform-specific shells and includes the user's $SHELL
        if it's not already in the list (supports any shell).

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

        # Include user's $SHELL if not already detected (supports unknown shells)
        user_shell = self._create_shell_from_env()
        if user_shell and not any(s.id == user_shell.id for s in shells):
            # Insert at beginning so user's preferred shell is first
            shells.insert(0, user_shell)

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

        On Windows, discovers shells from:
        - Windows Terminal profiles (includes WSL distros)
        - Hardcoded common shells (PowerShell, CMD, Git Bash)
        - Visual Studio Developer shells

        Note: WSL distros are detected from Windows Terminal profiles only.
        We don't probe inside WSL for individual shells to avoid crossing
        environment boundaries.

        Returns:
            List of (name, id, command, args) tuples.
        """
        if sys.platform == "win32":
            wt_profiles = self._get_windows_terminal_profiles()
            hardcoded = [
                ("PS 7", "pwsh", "pwsh.exe", ["-NoLogo"]),
                ("PS", "powershell", "powershell.exe", ["-NoLogo"]),
                ("CMD", "cmd", "cmd.exe", []),
                ("WSL", "wsl", "wsl.exe", []),
                ("Git Bash", "gitbash", r"C:\Program Files\Git\bin\bash.exe", ["--login"]),
            ]
            merged = self._merge_candidates(wt_profiles, hardcoded)
            vs_shells = self._get_visual_studio_shells()
            return merged + vs_shells
        return [
            ("Bash", "bash", "bash", ["--login"]),
            ("Zsh", "zsh", "zsh", ["--login"]),
            ("Fish", "fish", "fish", []),
            ("Nu", "nu", "nu", []),
            ("Ion", "ion", "ion", []),
            ("Dash", "dash", "dash", []),
            ("Ksh", "ksh", "ksh", ["--login"]),
            ("Tcsh", "tcsh", "tcsh", []),
            ("Sh", "sh", "sh", []),
        ]

    def _get_windows_terminal_profiles(self) -> list[tuple[str, str, str, list[str]]]:
        """Read shell profiles from Windows Terminal settings.json.

        Returns:
            List of (name, id, command, args) tuples from Windows Terminal.
        """
        settings_path = Path(
            os.environ.get("LOCALAPPDATA", ""),
            "Packages",
            "Microsoft.WindowsTerminal_8wekyb3d8bbwe",
            "LocalState",
            "settings.json",
        )

        if not settings_path.exists():
            return []

        try:
            # Read and parse JSON (WT uses JSON with comments, strip them)
            content = settings_path.read_text(encoding="utf-8")
            content = self._strip_json_comments(content)
            data = json.loads(content)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Failed to read Windows Terminal settings: %s", e)
            return []

        profiles = []
        profile_list = data.get("profiles", {}).get("list", [])

        for profile in profile_list:
            name = profile.get("name", "")
            commandline = profile.get("commandline", "")
            source = profile.get("source", "")

            if not name:
                continue

            # Handle WSL distro profiles (they use source instead of commandline)
            if source == "Windows.Terminal.Wsl" and not commandline:
                # Use wsl.exe -d <distro> to launch the specific distro
                shell_id = self._slugify(name)
                short_name = self._abbreviate_name(name)
                profiles.append((short_name, shell_id, "wsl.exe", ["-d", name]))
                continue

            if not commandline:
                continue

            # Parse commandline into command and args
            command, args = self._parse_commandline(commandline)
            if not command:
                continue

            # Expand environment variables in command path
            command = os.path.expandvars(command)

            # Create a slug ID from the name
            shell_id = self._slugify(name)

            # Shorten display name
            short_name = self._abbreviate_name(name)

            profiles.append((short_name, shell_id, command, args))

        return profiles

    def _get_visual_studio_shells(self) -> list[tuple[str, str, str, list[str]]]:
        """Detect Visual Studio Developer Command Prompts and PowerShells.

        Returns:
            List of (name, id, command, args) tuples for VS dev shells.
        """
        vswhere = Path(
            os.environ.get("ProgramFiles(x86)", ""),
            "Microsoft Visual Studio",
            "Installer",
            "vswhere.exe",
        )

        if not vswhere.exists():
            return []

        try:
            result = subprocess.run(
                [str(vswhere), "-all", "-prerelease", "-format", "json"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            vs_installs = json.loads(result.stdout) if result.stdout.strip() else []
        except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError) as e:
            logger.warning("Failed to run vswhere: %s", e)
            return []

        shells = []
        for vs_info in vs_installs:
            vs_path = Path(vs_info.get("installationPath", ""))
            instance_id = vs_info.get("instanceId", "")
            # Extract VS version and edition from path
            # e.g., "C:\Program Files\Microsoft Visual Studio\2022\Community"
            edition = vs_path.name  # Community, Professional, Enterprise
            year = vs_path.parent.name  # 2022, 2019, etc.

            # Developer Command Prompt (CMD)
            vsdevcmd = vs_path / "Common7" / "Tools" / "VsDevCmd.bat"
            if vsdevcmd.exists():
                name = f"Dev CMD {year}"
                shell_id = f"devcmd-{year}-{edition.lower()}"
                # cmd.exe /k "path\to\VsDevCmd.bat"
                shells.append(
                    (
                        name,
                        shell_id,
                        "cmd.exe",
                        ["/k", str(vsdevcmd)],
                    )
                )

            # Developer PowerShell - find DevShell.dll (location varies by VS version)
            devshell_dll = None
            for dll_path in [
                vs_path / "Common7" / "Tools" / "Microsoft.VisualStudio.DevShell.dll",
                vs_path
                / "Common7"
                / "Tools"
                / "vsdevshell"
                / "Microsoft.VisualStudio.DevShell.dll",
            ]:
                if dll_path.exists():
                    devshell_dll = dll_path
                    break

            if devshell_dll and instance_id:
                name = f"Dev PS {year}"
                shell_id = f"devps-{year}-{edition.lower()}"
                # Use forward slashes to avoid backslash escape issues (PowerShell accepts both)
                dll_str = str(devshell_dll).replace("\\", "/")
                cmd = f"Import-Module '{dll_str}'; Enter-VsDevShell {instance_id} -SkipAutomaticLocation"
                shells.append(
                    (
                        name,
                        shell_id,
                        "powershell.exe",
                        ["-NoExit", "-Command", cmd],
                    )
                )

        return shells

    def _strip_json_comments(self, content: str) -> str:
        """Strip comments from JSON content while preserving strings.

        Handles:
        - Single-line comments: // comment
        - Multi-line comments: /* comment */
        - Preserves // inside quoted strings (e.g., URLs)

        Args:
            content: JSON content with possible comments

        Returns:
            JSON content without comments
        """
        result = []
        i = 0
        in_string = False
        escape_next = False

        while i < len(content):
            char = content[i]

            if escape_next:
                result.append(char)
                escape_next = False
                i += 1
                continue

            if char == "\\" and in_string:
                result.append(char)
                escape_next = True
                i += 1
                continue

            if char == '"' and not escape_next:
                in_string = not in_string
                result.append(char)
                i += 1
                continue

            if not in_string:
                # Check for single-line comment
                if content[i : i + 2] == "//":
                    # Skip to end of line
                    while i < len(content) and content[i] != "\n":
                        i += 1
                    continue
                # Check for multi-line comment
                if content[i : i + 2] == "/*":
                    i += 2
                    while i < len(content) - 1 and content[i : i + 2] != "*/":
                        i += 1
                    i += 2  # Skip */
                    continue

            result.append(char)
            i += 1

        return "".join(result)

    def _parse_commandline(self, commandline: str) -> tuple[str, list[str]]:
        """Parse a commandline string into command and args.

        Args:
            commandline: The command line string (e.g., 'cmd.exe /k "vcvars64.bat"')

        Returns:
            Tuple of (command, args_list)
        """
        try:
            # Use shlex to properly handle quoted arguments
            parts = shlex.split(commandline, posix=False)
            if not parts:
                return "", []
            return parts[0], parts[1:]
        except ValueError:
            # Fallback: simple split on first space
            parts = commandline.split(None, 1)
            if not parts:
                return "", []
            return parts[0], parts[1:] if len(parts) > 1 else []

    def _abbreviate_name(self, name: str) -> str:
        """Abbreviate a shell name for display.

        Args:
            name: Full shell name (e.g., "Windows PowerShell")

        Returns:
            Abbreviated name (e.g., "WinPS")
        """
        # Common abbreviations
        abbrevs = {
            "Windows PowerShell": "WinPS",
            "Command Prompt": "CMD",
            "PowerShell": "PS",
            "Developer Command Prompt": "DevCMD",
            "Developer PowerShell": "DevPS",
            "Azure Cloud Shell": "Azure",
            "Git Bash": "GitBash",
        }

        # Check for exact or prefix match
        for full, short in abbrevs.items():
            if name == full or name.startswith(full):
                # Append suffix if there's more (e.g., "for VS 2022")
                suffix = name[len(full) :].strip()
                if suffix:
                    # Extract version/year if present
                    parts = suffix.split()
                    for part in parts:
                        if part.isdigit() and len(part) == 4:  # Year like 2022
                            return f"{short} {part}"
                return short

        # Fallback: first 8 chars if name is long
        if len(name) > 10:
            return name[:8].strip()
        return name

    def _slugify(self, name: str) -> str:
        """Convert a profile name to a slug ID.

        Args:
            name: Profile name (e.g., "Developer PowerShell for VS 2022")

        Returns:
            Slug ID (e.g., "developer-powershell-for-vs-2022")
        """
        # Lowercase, replace non-alphanumeric with hyphens, collapse multiple hyphens
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower())
        return slug.strip("-")

    def _merge_candidates(
        self,
        primary: list[tuple[str, str, str, list[str]]],
        secondary: list[tuple[str, str, str, list[str]]],
    ) -> list[tuple[str, str, str, list[str]]]:
        """Merge two candidate lists, deduplicating by command executable.

        Args:
            primary: First list (takes priority)
            secondary: Second list (skipped if command already in primary)

        Returns:
            Merged and deduplicated list
        """
        result = list(primary)
        seen_commands = set()

        # Track commands from primary (normalize to lowercase basename)
        for _, _, command, _ in primary:
            cmd_name = Path(command).name.lower()
            seen_commands.add(cmd_name)

        # Add secondary items if command not already seen
        for item in secondary:
            cmd_name = Path(item[2]).name.lower()
            if cmd_name not in seen_commands:
                result.append(item)
                seen_commands.add(cmd_name)

        return result

    def _get_windows_default(self) -> str:
        """Get default shell ID for Windows."""
        if shutil.which("pwsh.exe"):
            return "pwsh"
        if shutil.which("powershell.exe"):
            return "powershell"
        return "cmd"

    def _get_macos_default(self) -> str:
        """Get default shell ID for macOS."""
        # Check user's configured shell from $SHELL
        user_shell = self._get_user_shell_id()
        if user_shell:
            return user_shell
        # Fallback to zsh (macOS default since Catalina)
        if shutil.which("zsh"):
            return "zsh"
        return "bash"

    def _get_linux_default(self) -> str:
        """Get default shell ID for Linux."""
        # Check user's configured shell from $SHELL
        user_shell = self._get_user_shell_id()
        if user_shell:
            return user_shell
        # Fallback
        if shutil.which("bash"):
            return "bash"
        if shutil.which("zsh"):
            return "zsh"
        return "sh"

    def _get_user_shell_id(self) -> str | None:
        """Get shell ID from user's $SHELL environment variable.

        Returns:
            Shell ID if $SHELL is set and valid, None otherwise.
            For unknown shells, returns the executable name as the ID.
        """
        shell_path = os.environ.get("SHELL", "")
        if not shell_path:
            return None

        path = Path(shell_path)

        # Validate shell exists
        if not path.exists() and not shutil.which(shell_path):
            return None

        # Extract shell name from path (e.g., /usr/bin/fish -> fish)
        shell_name = path.name.lower()

        # Map common shell names to canonical IDs (for consistency)
        shell_map = {
            "bash": "bash",
            "zsh": "zsh",
            "fish": "fish",
            "sh": "sh",
        }

        # Return known ID or use executable name for unknown shells
        return shell_map.get(shell_name, shell_name)

    def _create_shell_from_env(self) -> ShellCommand | None:
        """Create a ShellCommand from user's $SHELL environment variable.

        Returns:
            ShellCommand if $SHELL is set and valid, None otherwise.
        """
        shell_path = os.environ.get("SHELL", "")
        if not shell_path:
            return None

        path = Path(shell_path)

        # Validate shell exists
        if not path.exists() and not shutil.which(shell_path):
            return None

        shell_name = path.name.lower()

        # Known shells with their display names and args
        known_shells = {
            "bash": ("Bash", ["--login"]),
            "zsh": ("Zsh", ["--login"]),
            "fish": ("Fish", []),
            "sh": ("Sh", []),
        }

        if shell_name in known_shells:
            display_name, args = known_shells[shell_name]
        else:
            # Unknown shell - use capitalized name, no special args
            display_name = shell_name.capitalize()
            args = []

        return ShellCommand(
            id=shell_name,
            name=display_name,
            command=shell_path,
            args=tuple(args),
        )
