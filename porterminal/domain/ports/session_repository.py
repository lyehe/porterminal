"""Session repository port - interface for session storage."""

from abc import ABC, abstractmethod
from typing import TypeVar

from ..entities.session import Session
from ..values.session_id import SessionId
from ..values.user_id import UserId

PTYHandle = TypeVar("PTYHandle")


class SessionRepository[PTYHandle](ABC):
    """Abstract interface for session storage.

    Infrastructure layer provides concrete implementation.
    Methods are synchronous - async wrapping is infrastructure concern.
    """

    @abstractmethod
    def get(self, session_id: SessionId) -> Session[PTYHandle] | None:
        """Get session by ID."""
        ...

    @abstractmethod
    def get_by_id_str(self, session_id: str) -> Session[PTYHandle] | None:
        """Get session by ID string (convenience method)."""
        ...

    @abstractmethod
    def get_by_user(self, user_id: UserId) -> list[Session[PTYHandle]]:
        """Get all sessions for a user."""
        ...

    @abstractmethod
    def add(self, session: Session[PTYHandle]) -> None:
        """Add a new session."""
        ...

    @abstractmethod
    def remove(self, session_id: SessionId) -> Session[PTYHandle] | None:
        """Remove and return a session."""
        ...

    @abstractmethod
    def count(self) -> int:
        """Get total session count."""
        ...

    @abstractmethod
    def count_for_user(self, user_id: UserId) -> int:
        """Get session count for a user."""
        ...

    @abstractmethod
    def all_sessions(self) -> list[Session[PTYHandle]]:
        """Get all sessions (for cleanup iteration)."""
        ...
