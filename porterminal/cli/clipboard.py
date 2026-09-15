"""Cross-platform clipboard copy using built-in OS tools (no extra dependency).

Mirrors the project's "try the platform tool, fall through gracefully" approach
(see CloudflaredInstaller). No third-party clipboard library is required.
"""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
import sys
import time
from enum import Enum

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


class CopyResult(Enum):
    """Outcome of :func:`copy_to_clipboard`, from most to least certain."""

    COPIED = "copied"
    """A system clipboard tool confirmed the write."""

    SENT_TO_TERMINAL = "sent_to_terminal"
    """An OSC52 sequence was written; terminals never acknowledge it, so the
    clipboard may or may not hold the text."""

    UNAVAILABLE = "unavailable"
    """No clipboard path worked."""

    def __bool__(self) -> bool:
        """Truthy only for a confirmed copy, so ``if copy_to_clipboard(...)`` cannot lie."""
        return self is CopyResult.COPIED


class _ToolOutcome(Enum):
    """Result of one clipboard-tool invocation."""

    OK = "ok"
    FAILED = "failed"  # non-zero exit or OS error: worth one retry
    MISSING = "missing"  # binary not installed: retrying cannot help
    TIMED_OUT = "timed_out"  # hung: retrying would only multiply the freeze


def _run_tool(cmd: list[str], text: str, *, timeout: float) -> _ToolOutcome:
    """Pipe ``text`` into a clipboard command's stdin and classify the outcome."""
    try:
        # Never capture stdout/stderr: wl-copy and xclip fork a daemon that
        # inherits them and keeps serving the clipboard until it is replaced,
        # so a captured pipe never reaches EOF and every call hits the timeout.
        subprocess.run(
            cmd,
            input=text,
            text=True,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
        return _ToolOutcome.OK
    except FileNotFoundError:
        return _ToolOutcome.MISSING
    except subprocess.TimeoutExpired:
        return _ToolOutcome.TIMED_OUT
    except (OSError, ValueError, subprocess.SubprocessError):
        # ValueError covers UnicodeEncodeError from text=True.
        return _ToolOutcome.FAILED


def _pipe_to(cmd: list[str], text: str, *, timeout: float = 3) -> bool:
    """Pipe ``text`` into a clipboard command's stdin. Return True on success."""
    return _run_tool(cmd, text, timeout=timeout) is _ToolOutcome.OK


def _pipe_to_with_retries(
    cmd: list[str],
    text: str,
    *,
    timeout: float = 3,
    retry_delays: tuple[float, ...] = (),
) -> bool:
    """Retry a failed run; a missing or hung tool is not worth retrying."""
    outcome = _run_tool(cmd, text, timeout=timeout)
    for delay in retry_delays:
        if outcome is not _ToolOutcome.FAILED:
            break
        time.sleep(delay)
        outcome = _run_tool(cmd, text, timeout=timeout)
    return outcome is _ToolOutcome.OK


def _copy_to_first_available(
    commands: tuple[list[str], ...],
    text: str,
    *,
    timeout: float = 3,
    retry_delays: tuple[float, ...] = (),
) -> bool:
    """Try fallback commands and retry the full list only on transient failures."""
    for attempt in range(len(retry_delays) + 1):
        if attempt > 0:
            time.sleep(retry_delays[attempt - 1])
        retryable = False
        for cmd in commands:
            outcome = _run_tool(cmd, text, timeout=timeout)
            if outcome is _ToolOutcome.OK:
                return True
            if outcome is _ToolOutcome.TIMED_OUT:
                # A hung tool means a broken display session; the next tool
                # would hang too, so cap the freeze at one timeout.
                return False
            retryable |= outcome is _ToolOutcome.FAILED
        if not retryable:
            return False  # Nothing installed, or nothing worth retrying.
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


def clipboard_install_hint() -> str | None:
    """Return a one-line install hint when a Linux desktop has no clipboard tool.

    Ubuntu desktop ships none of wl-clipboard/xclip/xsel, so a copy failure there
    is almost always a missing tool rather than a transient error. Windows,
    macOS and WSL always have a built-in command, and a headless or SSH session
    has no display for any tool to talk to, so those get no hint.
    """
    if sys.platform in ("win32", "darwin") or _is_wsl():
        return None

    session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
    wayland = bool(os.environ.get("WAYLAND_DISPLAY")) or session_type == "wayland"
    x11 = bool(os.environ.get("DISPLAY")) or session_type == "x11"
    if not (wayland or x11):
        return None
    if any(shutil.which(cmd[0]) for cmd in _LINUX_CLIPBOARD_COMMANDS):
        return None
    if wayland:
        return "Install wl-clipboard to enable clipboard copy"
    return "Install xclip or xsel to enable clipboard copy"


def _copy_to_terminal_clipboard(text: str) -> bool:
    """Send an OSC52 clipboard sequence to an interactive terminal."""
    if os.environ.get(_OSC52_DISABLE_ENV, "").lower() in _TRUE_ENV_VALUES:
        return False
    # VTE-based terminals (GNOME Terminal, Tilix, Ptyxis, ...) export VTE_VERSION
    # and silently drop OSC52 (https://gitlab.gnome.org/GNOME/vte/-/issues/2495),
    # so reporting success here would hide the URL behind a false "Copied".
    if os.environ.get("VTE_VERSION"):
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


def copy_to_clipboard(text: str) -> CopyResult:
    """Copy ``text`` to the system clipboard using built-in OS utilities.

    Platform tools used (no third-party dependency):
    - Windows: ``clip``
    - macOS:   ``pbcopy``
    - Linux:   WSL clipboard, Wayland, then X11 tools (first one available)
    - Fallback: OSC52 terminal clipboard sequence when running interactively
      (skipped in VTE-based terminals, which ignore it)

    Args:
        text: The text to place on the clipboard.

    Returns:
        ``COPIED`` if a platform tool succeeded, ``SENT_TO_TERMINAL`` if only
        the unconfirmable OSC52 sequence was written, else ``UNAVAILABLE``.
    """
    if _copy_to_system_clipboard(text):
        return CopyResult.COPIED
    if _copy_to_terminal_clipboard(text):
        return CopyResult.SENT_TO_TERMINAL
    return CopyResult.UNAVAILABLE
