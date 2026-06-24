"""Cross-platform clipboard copy using built-in OS tools (no extra dependency).

Mirrors the project's "try the platform tool, fall through gracefully" approach
(see CloudflaredInstaller). No third-party clipboard library is required.
"""

from __future__ import annotations

import subprocess
import sys

# Linux clipboard utilities, tried in order: Wayland first, then X11 variants.
# None is guaranteed to be installed, so we try each and report failure if all miss.
_LINUX_CLIPBOARD_COMMANDS: tuple[list[str], ...] = (
    ["wl-copy"],
    ["xclip", "-selection", "clipboard"],
    ["xsel", "--clipboard", "--input"],
)


def _pipe_to(cmd: list[str], text: str) -> bool:
    """Pipe ``text`` into a clipboard command's stdin. Return True on success."""
    try:
        subprocess.run(
            cmd,
            input=text,
            text=True,
            check=True,
            capture_output=True,
            timeout=3,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        # FileNotFoundError (tool missing), non-zero exit, or timeout.
        return False


def copy_to_clipboard(text: str) -> bool:
    """Copy ``text`` to the system clipboard using built-in OS utilities.

    Platform tools used (no third-party dependency):
    - Windows: ``clip``
    - macOS:   ``pbcopy``
    - Linux:   ``wl-copy`` -> ``xclip`` -> ``xsel`` (first one available)

    Args:
        text: The text to place on the clipboard.

    Returns:
        True if the text was copied; False if no clipboard tool was available or
        the copy failed (e.g. a headless Linux box with no clipboard server).
    """
    if sys.platform == "win32":
        return _pipe_to(["clip"], text)
    if sys.platform == "darwin":
        return _pipe_to(["pbcopy"], text)
    # Linux / other Unix: try each tool until one succeeds.
    return any(_pipe_to(cmd, text) for cmd in _LINUX_CLIPBOARD_COMMANDS)
