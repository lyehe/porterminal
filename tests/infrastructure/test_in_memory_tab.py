"""Tests for InMemoryTabRepository."""

from datetime import UTC, datetime, timedelta

from porterminal.domain import SessionId, Tab, TabId, UserId
from porterminal.infrastructure.repositories import InMemoryTabRepository


class TestInMemoryTabRepository:
    """Tests for InMemoryTabRepository."""

    # ============= Basic CRUD =============

    def test_add_and_get(self, sample_tab):
        """Test adding and retrieving a tab."""
        repo = InMemoryTabRepository()

        repo.add(sample_tab)
        retrieved = repo.get(sample_tab.id)

        assert retrieved is sample_tab

    def test_get_by_id_str(self, sample_tab):
        """Test getting tab by ID string."""
        repo = InMemoryTabRepository()
        repo.add(sample_tab)

        retrieved = repo.get_by_id_str(str(sample_tab.id))

        assert retrieved is sample_tab

    def test_get_nonexistent_returns_none(self):
        """Test getting non-existent tab returns None."""
        repo = InMemoryTabRepository()

        result = repo.get(TabId("nonexistent"))

        assert result is None

    def test_update_existing_tab(self, sample_tab):
        """Test updating an existing tab."""
        repo = InMemoryTabRepository()
        repo.add(sample_tab)

        # Modify and update
        sample_tab.rename("Updated Name")
        repo.update(sample_tab)

        retrieved = repo.get(sample_tab.id)
        assert retrieved.name == "Updated Name"

    def test_update_nonexistent_silent(self, sample_tab):
        """Test updating non-existent tab is silent (no error)."""
        repo = InMemoryTabRepository()

        # Should not raise
        repo.update(sample_tab)

        # Still not in repo
        assert repo.get(sample_tab.id) is None

    def test_remove_returns_tab(self, sample_tab):
        """Test removing a tab returns the removed tab."""
        repo = InMemoryTabRepository()
        repo.add(sample_tab)

        removed = repo.remove(sample_tab.id)

        assert removed is sample_tab
        assert repo.get(sample_tab.id) is None

    def test_remove_nonexistent_returns_none(self):
        """Test removing non-existent tab returns None."""
        repo = InMemoryTabRepository()

        removed = repo.remove(TabId("nonexistent"))

        assert removed is None

    # ============= Query Operations =============

    def test_get_by_user_returns_sorted_by_created_at(self, user_id, session_id):
        """Test get_by_user returns tabs sorted by created_at ASC."""
        repo = InMemoryTabRepository()
        now = datetime.now(UTC)

        # Add tabs in reverse order
        tab3 = Tab(
            id=TabId("tab-3"),
            user_id=user_id,
            session_id=session_id,
            shell_id="bash",
            name="Tab 3",
            created_at=now + timedelta(hours=2),
            last_accessed=now,
        )
        tab1 = Tab(
            id=TabId("tab-1"),
            user_id=user_id,
            session_id=session_id,
            shell_id="bash",
            name="Tab 1",
            created_at=now,
            last_accessed=now,
        )
        tab2 = Tab(
            id=TabId("tab-2"),
            user_id=user_id,
            session_id=session_id,
            shell_id="bash",
            name="Tab 2",
            created_at=now + timedelta(hours=1),
            last_accessed=now,
        )

        repo.add(tab3)
        repo.add(tab1)
        repo.add(tab2)

        user_tabs = repo.get_by_user(user_id)

        assert len(user_tabs) == 3
        assert user_tabs[0].name == "Tab 1"
        assert user_tabs[1].name == "Tab 2"
        assert user_tabs[2].name == "Tab 3"

    def test_get_by_user_empty_list(self, user_id):
        """Test get_by_user returns empty list for user with no tabs."""
        repo = InMemoryTabRepository()

        user_tabs = repo.get_by_user(user_id)

        assert user_tabs == []

    def test_get_by_user_multiple_tabs(self, sample_tab, user_id, session_id):
        """Test get_by_user returns all tabs for user."""
        repo = InMemoryTabRepository()
        repo.add(sample_tab)

        now = datetime.now(UTC)
        tab2 = Tab(
            id=TabId("tab-2"),
            user_id=user_id,
            session_id=session_id,
            shell_id="zsh",
            name="Tab 2",
            created_at=now,
            last_accessed=now,
        )
        repo.add(tab2)

        user_tabs = repo.get_by_user(user_id)

        assert len(user_tabs) == 2

    def test_get_by_session_returns_all(self, user_id, session_id):
        """Test get_by_session returns all tabs for a session."""
        repo = InMemoryTabRepository()
        now = datetime.now(UTC)

        tab1 = Tab(
            id=TabId("tab-1"),
            user_id=user_id,
            session_id=session_id,
            shell_id="bash",
            name="Tab 1",
            created_at=now,
            last_accessed=now,
        )
        tab2 = Tab(
            id=TabId("tab-2"),
            user_id=user_id,
            session_id=session_id,
            shell_id="bash",
            name="Tab 2",
            created_at=now,
            last_accessed=now,
        )
        repo.add(tab1)
        repo.add(tab2)

        session_tabs = repo.get_by_session(session_id)

        assert len(session_tabs) == 2

    def test_get_by_session_empty(self, session_id):
        """Test get_by_session returns empty list for session with no tabs."""
        repo = InMemoryTabRepository()

        session_tabs = repo.get_by_session(session_id)

        assert session_tabs == []

    # ============= Cascade Operations =============

    def test_remove_by_session_cascades_all_tabs(self, user_id, session_id):
        """Test remove_by_session removes all tabs for session."""
        repo = InMemoryTabRepository()
        now = datetime.now(UTC)

        tab1 = Tab(
            id=TabId("tab-1"),
            user_id=user_id,
            session_id=session_id,
            shell_id="bash",
            name="Tab 1",
            created_at=now,
            last_accessed=now,
        )
        tab2 = Tab(
            id=TabId("tab-2"),
            user_id=user_id,
            session_id=session_id,
            shell_id="bash",
            name="Tab 2",
            created_at=now,
            last_accessed=now,
        )
        repo.add(tab1)
        repo.add(tab2)

        removed = repo.remove_by_session(session_id)

        assert len(removed) == 2
        assert repo.count() == 0

    def test_remove_by_session_cleans_user_index(self, user_id, session_id):
        """Test remove_by_session also cleans up user index."""
        repo = InMemoryTabRepository()
        now = datetime.now(UTC)

        tab = Tab(
            id=TabId("tab-1"),
            user_id=user_id,
            session_id=session_id,
            shell_id="bash",
            name="Tab 1",
            created_at=now,
            last_accessed=now,
        )
        repo.add(tab)
        assert repo.count_for_user(user_id) == 1

        repo.remove_by_session(session_id)

        assert repo.count_for_user(user_id) == 0

    def test_remove_by_session_empty_session(self, session_id):
        """Test remove_by_session returns empty list for empty session."""
        repo = InMemoryTabRepository()

        removed = repo.remove_by_session(session_id)

        assert removed == []

    # ============= Count Operations =============

    def test_count_empty(self):
        """Test count returns 0 for empty repository."""
        repo = InMemoryTabRepository()

        assert repo.count() == 0

    def test_count_after_add(self, sample_tab):
        """Test count increases after adding tabs."""
        repo = InMemoryTabRepository()

        repo.add(sample_tab)

        assert repo.count() == 1

    def test_count_after_remove(self, sample_tab):
        """Test count decreases after removing tabs."""
        repo = InMemoryTabRepository()
        repo.add(sample_tab)

        repo.remove(sample_tab.id)

        assert repo.count() == 0

    def test_count_for_user_isolated(self, sample_tab, user_id):
        """Test count_for_user only counts user's tabs."""
        repo = InMemoryTabRepository()
        repo.add(sample_tab)

        # Add tab for different user
        now = datetime.now(UTC)
        other_tab = Tab(
            id=TabId("other-tab"),
            user_id=UserId("other-user"),
            session_id=SessionId("other-session"),
            shell_id="bash",
            name="Other Tab",
            created_at=now,
            last_accessed=now,
        )
        repo.add(other_tab)

        assert repo.count_for_user(user_id) == 1
        assert repo.count_for_user(UserId("other-user")) == 1
        assert repo.count() == 2

    def test_count_for_user_multiple_users(self, user_id, session_id):
        """Test count_for_user correctly isolates counts."""
        repo = InMemoryTabRepository()
        now = datetime.now(UTC)

        # Add 3 tabs for user
        for i in range(3):
            tab = Tab(
                id=TabId(f"tab-{i}"),
                user_id=user_id,
                session_id=session_id,
                shell_id="bash",
                name=f"Tab {i}",
                created_at=now,
                last_accessed=now,
            )
            repo.add(tab)

        # Add 2 tabs for other user
        other_user = UserId("other-user")
        for i in range(2):
            tab = Tab(
                id=TabId(f"other-tab-{i}"),
                user_id=other_user,
                session_id=SessionId("other-session"),
                shell_id="bash",
                name=f"Other Tab {i}",
                created_at=now,
                last_accessed=now,
            )
            repo.add(tab)

        assert repo.count_for_user(user_id) == 3
        assert repo.count_for_user(other_user) == 2
        assert repo.count() == 5

    # ============= Index Consistency =============

    def test_remove_cleans_all_indexes(self, sample_tab, user_id, session_id):
        """Test removing a tab cleans all index structures."""
        repo = InMemoryTabRepository()
        repo.add(sample_tab)

        repo.remove(sample_tab.id)

        # All lookups should return empty/None
        assert repo.get(sample_tab.id) is None
        assert repo.get_by_user(user_id) == []
        assert repo.get_by_session(session_id) == []

    def test_add_updates_all_indexes(self, sample_tab, user_id, session_id):
        """Test adding a tab updates all index structures."""
        repo = InMemoryTabRepository()

        repo.add(sample_tab)

        # All lookups should find the tab
        assert repo.get(sample_tab.id) is sample_tab
        assert sample_tab in repo.get_by_user(user_id)
        assert sample_tab in repo.get_by_session(session_id)
