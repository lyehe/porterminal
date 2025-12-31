"""Domain entities - objects with identity and lifecycle."""

from .output_buffer import CLEAR_SCREEN_SEQUENCE, OUTPUT_BUFFER_MAX_BYTES, OutputBuffer
from .session import MAX_SESSIONS_PER_USER, MAX_TOTAL_SESSIONS, Session
from .tab import MAX_TABS_PER_USER, Tab

__all__ = [
    "Session",
    "MAX_SESSIONS_PER_USER",
    "MAX_TOTAL_SESSIONS",
    "OutputBuffer",
    "OUTPUT_BUFFER_MAX_BYTES",
    "CLEAR_SCREEN_SEQUENCE",
    "Tab",
    "MAX_TABS_PER_USER",
]
