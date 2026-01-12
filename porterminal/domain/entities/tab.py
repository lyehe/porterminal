"""Tab entity - lightweight reference to a session."""

from dataclasses import dataclass
from datetime import datetime

from ..values.session_id import SessionId
from ..values.tab_id import TabId
from ..values.user_id import UserId

# Business rule constants
MAX_TABS_PER_USER = 20
TAB_NAME_MIN_LENGTH = 1
TAB_NAME_MAX_LENGTH = 50


def _validate_tab_name(name: str) -> None:
    """Validate tab name length."""
    if not (TAB_NAME_MIN_LENGTH <= len(name) <= TAB_NAME_MAX_LENGTH):
        raise ValueError(
            f"Tab name must be {TAB_NAME_MIN_LENGTH}-{TAB_NAME_MAX_LENGTH} "
            f"characters, got {len(name)}"
        )


@dataclass
class Tab:
    """Terminal tab entity.

    Lightweight entity that references a session.
    Does NOT hold PTY or any infrastructure references.

    Invariants:
    - Tab always references exactly one Session
    - Tab is owned by exactly one User (same user who owns the Session)
    - Tab name is 1-50 characters, non-empty
    """

    id: TabId
    user_id: UserId
    session_id: SessionId
    shell_id: str
    name: str
    created_at: datetime
    last_accessed: datetime

    def __post_init__(self) -> None:
        _validate_tab_name(self.name)

    @property
    def tab_id(self) -> str:
        """String representation of tab ID."""
        return str(self.id)

    def touch(self, now: datetime) -> None:
        """Update last accessed timestamp."""
        self.last_accessed = now

    def rename(self, new_name: str) -> None:
        """Rename the tab with validation."""
        _validate_tab_name(new_name)
        self.name = new_name

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": str(self.id),
            "session_id": str(self.session_id),
            "shell_id": self.shell_id,
            "name": self.name,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
        }
