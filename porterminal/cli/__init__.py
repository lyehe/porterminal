"""CLI utilities for Porterminal."""

from .args import parse_args
from .clipboard import copy_to_clipboard
from .display import (
    LOGO,
    TAGLINE_PORTABLE,
    TAGLINE_TERMINAL,
    display_connected_screen,
    display_startup_screen,
    get_qr_code,
)
from .keypress import start_key_listener
from .share import build_agent_share_text

__all__ = [
    "parse_args",
    "copy_to_clipboard",
    "build_agent_share_text",
    "start_key_listener",
    "display_connected_screen",
    "display_startup_screen",
    "get_qr_code",
    "LOGO",
    "TAGLINE_PORTABLE",
    "TAGLINE_TERMINAL",
]
