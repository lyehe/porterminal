"""Session limit checking service - pure business logic."""

from dataclasses import dataclass
from datetime import datetime
from typing import TypeVar

from ..entities.session import (
    MAX_SESSIONS_PER_USER,
    MAX_TOTAL_SESSIONS,
    RECONNECT_WINDOW_SECONDS,
    SESSION_MAX_DURATION_SECONDS,
    Session,
)
from ..values.user_id import UserId

PTYHandle = TypeVar("PTYHandle")


@dataclass(frozen=True)
class SessionLimitConfig:
    """Session limit configuration."""

    max_per_user: int = MAX_SESSIONS_PER_USER
    max_total: int = MAX_TOTAL_SESSIONS
    max_duration_seconds: int = SESSION_MAX_DURATION_SECONDS
    reconnect_window_seconds: int = RECONNECT_WINDOW_SECONDS


@dataclass
class SessionLimitResult:
    """Result of session limit check."""

    allowed: bool
    reason: str | None = None


class SessionLimitChecker:
    """Check session limits (pure business logic)."""

    def __init__(self, config: SessionLimitConfig | None = None) -> None:
        self.config = config or SessionLimitConfig()

    def can_create_session(
        self,
        user_id: UserId,
        user_session_count: int,
        total_session_count: int,
    ) -> SessionLimitResult:
        """Check if a new session can be created."""
        if user_session_count >= self.config.max_per_user:
            return SessionLimitResult(
                allowed=False,
                reason=f"Maximum sessions ({self.config.max_per_user}) reached for user",
            )

        if total_session_count >= self.config.max_total:
            return SessionLimitResult(
                allowed=False,
                reason="Server session limit reached",
            )

        return SessionLimitResult(allowed=True)

    def can_reconnect(
        self,
        session: Session,
        requesting_user: UserId,
    ) -> SessionLimitResult:
        """Check if user can reconnect to session."""
        if session.user_id != requesting_user:
            return SessionLimitResult(
                allowed=False,
                reason="Session belongs to another user",
            )
        return SessionLimitResult(allowed=True)

    def should_cleanup_session(
        self,
        session: Session,
        now: datetime,
        is_pty_alive: bool,
    ) -> tuple[bool, str | None]:
        """Check if a session should be cleaned up.

        Returns:
            Tuple of (should_cleanup, reason).
        """
        # Primary check: PTY dead = session dead
        if not is_pty_alive:
            return True, "PTY died"

        # Check max duration (0 = no limit)
        if self.config.max_duration_seconds > 0:
            age = (now - session.created_at).total_seconds()
            if age > self.config.max_duration_seconds:
                return True, "Exceeded max duration"

        # Check reconnection window (0 = no limit, only for disconnected sessions)
        if self.config.reconnect_window_seconds > 0 and not session.is_connected:
            idle = (now - session.last_activity).total_seconds()
            if idle > self.config.reconnect_window_seconds:
                return True, "Reconnection window expired"

        return False, None
