"""In-memory tab repository implementation."""

from porterminal.domain import SessionId, Tab, TabId, UserId
from porterminal.domain.ports import TabRepository


class InMemoryTabRepository(TabRepository):
    """In-memory tab storage implementing TabRepository.

    Thread-safe for async usage (dict operations are atomic in CPython).
    Uses dual-indexing for efficient lookups by user and session.
    """

    def __init__(self) -> None:
        self._tabs: dict[str, Tab] = {}
        self._user_tabs: dict[str, set[str]] = {}  # user_id -> {tab_ids}
        self._session_tabs: dict[str, set[str]] = {}  # session_id -> {tab_ids}

    def get(self, tab_id: TabId) -> Tab | None:
        """Get tab by ID."""
        return self._tabs.get(str(tab_id))

    def get_by_id_str(self, tab_id: str) -> Tab | None:
        """Get tab by ID string."""
        return self._tabs.get(tab_id)

    def get_by_user(self, user_id: UserId) -> list[Tab]:
        """Get all tabs for a user (ordered by created_at ASC)."""
        user_str = str(user_id)
        tab_ids = self._user_tabs.get(user_str, set())
        tabs = [self._tabs[tid] for tid in tab_ids if tid in self._tabs]
        return sorted(tabs, key=lambda t: t.created_at)

    def get_by_session(self, session_id: SessionId) -> list[Tab]:
        """Get all tabs referencing a specific session."""
        session_str = str(session_id)
        tab_ids = self._session_tabs.get(session_str, set())
        return [self._tabs[tid] for tid in tab_ids if tid in self._tabs]

    def add(self, tab: Tab) -> None:
        """Add a new tab."""
        tab_id = str(tab.id)
        user_id = str(tab.user_id)
        session_id = str(tab.session_id)

        self._tabs[tab_id] = tab
        self._user_tabs.setdefault(user_id, set()).add(tab_id)
        self._session_tabs.setdefault(session_id, set()).add(tab_id)

    def update(self, tab: Tab) -> None:
        """Update an existing tab (name, last_accessed)."""
        tab_id = str(tab.id)
        if tab_id in self._tabs:
            self._tabs[tab_id] = tab

    def remove(self, tab_id: TabId) -> Tab | None:
        """Remove and return a tab."""
        tab_id_str = str(tab_id)
        tab = self._tabs.pop(tab_id_str, None)

        if tab:
            user_id = str(tab.user_id)
            session_id = str(tab.session_id)

            # Clean up user index
            if user_id in self._user_tabs:
                self._user_tabs[user_id].discard(tab_id_str)
                if not self._user_tabs[user_id]:
                    del self._user_tabs[user_id]

            # Clean up session index
            if session_id in self._session_tabs:
                self._session_tabs[session_id].discard(tab_id_str)
                if not self._session_tabs[session_id]:
                    del self._session_tabs[session_id]

        return tab

    def remove_by_session(self, session_id: SessionId) -> list[Tab]:
        """Remove all tabs referencing a session (cascade).

        Returns:
            List of removed tabs.
        """
        session_str = str(session_id)
        tab_ids = list(self._session_tabs.get(session_str, set()))

        removed = []
        for tab_id_str in tab_ids:
            tab = self._tabs.pop(tab_id_str, None)
            if tab:
                removed.append(tab)
                # Clean up user index
                user_id = str(tab.user_id)
                if user_id in self._user_tabs:
                    self._user_tabs[user_id].discard(tab_id_str)
                    if not self._user_tabs[user_id]:
                        del self._user_tabs[user_id]

        # Clean up session index
        if session_str in self._session_tabs:
            del self._session_tabs[session_str]

        return removed

    def count(self) -> int:
        """Get total tab count."""
        return len(self._tabs)

    def count_for_user(self, user_id: UserId) -> int:
        """Get tab count for a user."""
        return len(self._user_tabs.get(str(user_id), set()))
