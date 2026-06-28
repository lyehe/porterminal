"""Cross-platform clipboard copy using built-in OS tools (no extra dependency).

Mirrors the project's "try the platform tool, fall through gracefully" approach
(see CloudflaredInstaller). No third-party clipboard library is required.
"""

from __future__ import annotations

import base64
import os
import subprocess
import sys
import time

# Linux clipboard utilities, tried in order after session-specific commands.
# None is guaranteed to be installed, so we try each and report failure if all miss.
_LINUX_CLIPBOARD_COMMANDS: tuple[list[str], ...] = (
    ["wl-copy"],
    ["xclip", "-selection", "clipboard"],
    ["xsel", "--clipboard", "--input"],
)
_LINUX_WSL_CLIPBOARD_COMMANDS: tuple[list[str], ...] = (
    ["clip.exe"],
    ["/mnt/c/Windows/System32/clip.exe"],
)
_LINUX_RETRY_DELAYS_SECONDS = (0.1, 0.3)
_MACOS_PBCOPY_COMMAND = ["/usr/bin/pbcopy"]
_MACOS_RETRY_DELAYS_SECONDS = (0.1, 0.3)
_OSC52_CLIPBOARD_MAX_BYTES = 100_000
_OSC52_DISABLE_ENV = "PORTERMINAL_DISABLE_OSC52_CLIPBOARD"
_TRUE_ENV_VALUES = {"1", "true", "yes", "on"}


def _pipe_to(cmd: list[str], text: str, *, timeout: float = 3) -> bool:
    """Pipe ``text`` into a clipboard command's stdin. Return True on success."""
    try:
        subprocess.run(
            cmd,
            input=text,
            text=True,
            check=True,
            capture_output=True,
            timeout=timeout,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        # FileNotFoundError (tool missing), non-zero exit, or timeout.
        return False


def _pipe_to_with_retries(
    cmd: list[str],
    text: str,
    *,
    timeout: float = 3,
    retry_delays: tuple[float, ...] = (),
) -> bool:
    """Retry transient clipboard command failures before giving up."""
    if _pipe_to(cmd, text, timeout=timeout):
        return True

    for delay in retry_delays:
        time.sleep(delay)
        if _pipe_to(cmd, text, timeout=timeout):
            return True

    return False


def _copy_to_first_available(
    commands: tuple[list[str], ...],
    text: str,
    *,
    timeout: float = 3,
    retry_delays: tuple[float, ...] = (),
) -> bool:
    """Try fallback commands and retry the full list on transient failures."""
    for attempt in range(len(retry_delays) + 1):
        if attempt > 0:
            time.sleep(retry_delays[attempt - 1])
        for cmd in commands:
            if _pipe_to(cmd, text, timeout=timeout):
                return True
    return False


def _is_wsl() -> bool:
    """Return True when running under Windows Subsystem for Linux."""
    if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
        return True
    try:
        with open("/proc/version", encoding="utf-8", errors="ignore") as version_file:
            return "microsoft" in version_file.read().lower()
    except OSError:
        return False


def _linux_clipboard_commands() -> tuple[list[str], ...]:
    """Return Linux clipboard commands ordered by the current session."""
    commands: list[list[str]] = []

    def add(command: list[str]) -> None:
        if command not in commands:
            commands.append(command)

    if _is_wsl():
        for command in _LINUX_WSL_CLIPBOARD_COMMANDS:
            add(command)

    session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if os.environ.get("WAYLAND_DISPLAY") or session_type == "wayland":
        add(["wl-copy"])
    if os.environ.get("DISPLAY") or session_type == "x11":
        add(["xclip", "-selection", "clipboard"])
        add(["xsel", "--clipboard", "--input"])

    for command in _LINUX_CLIPBOARD_COMMANDS:
        add(command)

    return tuple(commands)


def _copy_to_terminal_clipboard(text: str) -> bool:
    """Send an OSC52 clipboard sequence to an interactive terminal."""
    if os.environ.get(_OSC52_DISABLE_ENV, "").lower() in _TRUE_ENV_VALUES:
        return False

    raw = text.encode("utf-8")
    if len(raw) > _OSC52_CLIPBOARD_MAX_BYTES:
        return False

    stdout = getattr(sys, "stdout", None)
    try:
        if stdout is None or not stdout.isatty():
            return False
    except (AttributeError, OSError):
        return False

    sequence = "\x1b]52;c;" + base64.b64encode(raw).decode("ascii") + "\a"
    try:
        stdout.write(sequence)
        stdout.flush()
        return True
    except (AttributeError, OSError, UnicodeError, ValueError):
        return False


def _copy_to_system_clipboard(text: str) -> bool:
    """Copy to the OS clipboard using platform-native command-line tools."""
    if sys.platform == "win32":
        return _pipe_to(["clip"], text)
    if sys.platform == "darwin":
        return _pipe_to_with_retries(
            _MACOS_PBCOPY_COMMAND,
            text,
            retry_delays=_MACOS_RETRY_DELAYS_SECONDS,
        )
    # Linux / other Unix: try each tool until one succeeds.
    return _copy_to_first_available(
        _linux_clipboard_commands(),
        text,
        retry_delays=_LINUX_RETRY_DELAYS_SECONDS,
    )


def copy_to_clipboard(text: str) -> bool:
    """Copy ``text`` to the system clipboard using built-in OS utilities.

    Platform tools used (no third-party dependency):
    - Windows: ``clip``
    - macOS:   ``pbcopy``
    - Linux:   WSL clipboard, Wayland, then X11 tools (first one available)
    - Fallback: OSC52 terminal clipboard sequence when running interactively

    Args:
        text: The text to place on the clipboard.

    Returns:
        True if a platform tool succeeded or an OSC52 terminal clipboard
        sequence was sent; False if no clipboard path was available.
    """
    return _copy_to_system_clipboard(text) or _copy_to_terminal_clipboard(text)
