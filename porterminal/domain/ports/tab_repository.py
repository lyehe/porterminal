"""Tab repository port - interface for tab storage."""

from abc import ABC, abstractmethod

from ..entities.tab import Tab
from ..values.session_id import SessionId
from ..values.tab_id import TabId
from ..values.user_id import UserId


class TabRepository(ABC):
    """Abstract interface for tab storage.

    Infrastructure layer provides concrete implementation.
    Methods are synchronous - async wrapping is infrastructure concern.
    """

    @abstractmethod
    def get(self, tab_id: TabId) -> Tab | None:
        """Get tab by ID."""
        ...

    @abstractmethod
    def get_by_id_str(self, tab_id: str) -> Tab | None:
        """Get tab by ID string (convenience method)."""
        ...

    @abstractmethod
    def get_by_user(self, user_id: UserId) -> list[Tab]:
        """Get all tabs for a user (ordered by last_accessed DESC)."""
        ...

    @abstractmethod
    def get_by_session(self, session_id: SessionId) -> list[Tab]:
        """Get all tabs referencing a specific session."""
        ...

    @abstractmethod
    def add(self, tab: Tab) -> None:
        """Add a new tab."""
        ...

    @abstractmethod
    def update(self, tab: Tab) -> None:
        """Update an existing tab (name, last_accessed)."""
        ...

    @abstractmethod
    def remove(self, tab_id: TabId) -> Tab | None:
        """Remove and return a tab."""
        ...

    @abstractmethod
    def remove_by_session(self, session_id: SessionId) -> list[Tab]:
        """Remove all tabs referencing a session (cascade).

        Returns:
            List of removed tabs.
        """
        ...

    @abstractmethod
    def count(self) -> int:
        """Get total tab count."""
        ...

    @abstractmethod
    def count_for_user(self, user_id: UserId) -> int:
        """Get tab count for a user."""
        ...
