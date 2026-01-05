"""Pure domain layer - no infrastructure dependencies."""

# Entities
from .entities import (
    CLEAR_SCREEN_SEQUENCE,
    MAX_SESSIONS_PER_USER,
    MAX_TABS_PER_USER,
    MAX_TOTAL_SESSIONS,
    OUTPUT_BUFFER_MAX_BYTES,
    OutputBuffer,
    Session,
    Tab,
)

# Ports
from .ports import (
    PTYPort,
    SessionRepository,
    TabRepository,
)

# Services
from .services import (
    Clock,
    SessionLimitChecker,
    SessionLimitConfig,
    SessionLimitResult,
    TabLimitChecker,
    TabLimitConfig,
    TabLimitResult,
    TokenBucketRateLimiter,
)
from .values import (
    MAX_COLS,
    MAX_ROWS,
    MIN_COLS,
    MIN_ROWS,
    RateLimitConfig,
    SessionId,
    ShellCommand,
    TabId,
    TerminalDimensions,
    UserId,
)

__all__ = [
    # Values
    "TerminalDimensions",
    "MIN_COLS",
    "MAX_COLS",
    "MIN_ROWS",
    "MAX_ROWS",
    "SessionId",
    "UserId",
    "TabId",
    "ShellCommand",
    "RateLimitConfig",
    # Entities
    "Session",
    "MAX_SESSIONS_PER_USER",
    "MAX_TOTAL_SESSIONS",
    "OutputBuffer",
    "OUTPUT_BUFFER_MAX_BYTES",
    "CLEAR_SCREEN_SEQUENCE",
    "Tab",
    "MAX_TABS_PER_USER",
    # Services
    "TokenBucketRateLimiter",
    "Clock",
    "SessionLimitChecker",
    "SessionLimitConfig",
    "SessionLimitResult",
    "TabLimitChecker",
    "TabLimitConfig",
    "TabLimitResult",
    # Ports
    "SessionRepository",
    "TabRepository",
    "PTYPort",
]
