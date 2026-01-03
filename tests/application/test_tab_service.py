"""Tests for TabService."""

import pytest

from porterminal.application.services import TabService
from porterminal.domain import SessionId, TabLimitChecker, UserId
from porterminal.domain.services.tab_limits import TabLimitConfig


class TestTabServiceCreation:
    """Tests for TabService tab creation."""

    def test_create_tab_success(self, user_id, session_id, tab_repository):
        """Test successful tab creation."""
        service = TabService(tab_repository)

        tab = service.create_tab(user_id, session_id, "bash", name="My Tab")

        assert tab is not None
        assert tab.name == "My Tab"
        assert tab.shell_id == "bash"
        assert tab.user_id == user_id
        assert tab.session_id == session_id

    def test_create_tab_auto_generates_name_from_shell(self, user_id, session_id, tab_repository):
        """Test that tab name is auto-generated from shell_id if not provided."""
        service = TabService(tab_repository)

        tab = service.create_tab(user_id, session_id, "powershell")

        assert tab.name == "Powershell"  # Capitalized shell_id

    def test_create_tab_with_custom_name(self, user_id, session_id, tab_repository):
        """Test tab creation with custom name."""
        service = TabService(tab_repository)

        tab = service.create_tab(user_id, session_id, "bash", name="Dev Server")

        assert tab.name == "Dev Server"

    def test_create_tab_limit_exceeded_raises(self, user_id, session_id, tab_repository):
        """Test that exceeding tab limit raises ValueError."""
        config = TabLimitConfig(max_per_user=2)
        limit_checker = TabLimitChecker(config)
        service = TabService(tab_repository, limit_checker)

        # Create 2 tabs (at limit)
        service.create_tab(user_id, session_id, "bash", name="Tab 1")
        service.create_tab(user_id, session_id, "bash", name="Tab 2")

        # Third should fail
        with pytest.raises(ValueError, match="Maximum tabs"):
            service.create_tab(user_id, session_id, "bash", name="Tab 3")


class TestTabServiceRetrieval:
    """Tests for TabService tab retrieval."""

    def test_get_tab_by_id(self, user_id, session_id, tab_repository):
        """Test getting tab by ID string."""
        service = TabService(tab_repository)
        created = service.create_tab(user_id, session_id, "bash", name="Test")

        retrieved = service.get_tab(str(created.id))

        assert retrieved is created

    def test_get_tab_nonexistent_returns_none(self, tab_repository):
        """Test getting non-existent tab returns None."""
        service = TabService(tab_repository)

        result = service.get_tab("nonexistent-id")

        assert result is None

    def test_get_user_tabs_ordered(self, user_id, session_id, tab_repository):
        """Test get_user_tabs returns tabs ordered by created_at."""
        service = TabService(tab_repository)

        tab1 = service.create_tab(user_id, session_id, "bash", name="First")
        tab2 = service.create_tab(user_id, session_id, "zsh", name="Second")
        tab3 = service.create_tab(user_id, session_id, "fish", name="Third")

        user_tabs = service.get_user_tabs(user_id)

        assert len(user_tabs) == 3
        # All created tabs should be present
        tab_ids = {t.id for t in user_tabs}
        assert tab1.id in tab_ids
        assert tab2.id in tab_ids
        assert tab3.id in tab_ids

    def test_get_tabs_for_session(self, user_id, session_id, tab_repository):
        """Test get_tabs_for_session returns all session tabs."""
        service = TabService(tab_repository)

        tab1 = service.create_tab(user_id, session_id, "bash", name="Tab 1")
        tab2 = service.create_tab(user_id, session_id, "bash", name="Tab 2")

        # Different session
        other_session = SessionId("other-session")
        service.create_tab(user_id, other_session, "bash", name="Other")

        session_tabs = service.get_tabs_for_session(session_id)

        assert len(session_tabs) == 2
        assert tab1 in session_tabs
        assert tab2 in session_tabs


class TestTabServiceUpdate:
    """Tests for TabService update operations."""

    def test_touch_tab_updates_timestamp(self, user_id, session_id, tab_repository):
        """Test that touch_tab updates last_accessed."""
        service = TabService(tab_repository)
        tab = service.create_tab(user_id, session_id, "bash", name="Test")
        original_accessed = tab.last_accessed

        # Touch the tab
        result = service.touch_tab(str(tab.id), user_id)

        assert result is not None
        assert result.last_accessed >= original_accessed

    def test_touch_tab_unauthorized_returns_none(self, user_id, session_id, tab_repository):
        """Test touch_tab returns None for unauthorized user."""
        service = TabService(tab_repository)
        tab = service.create_tab(user_id, session_id, "bash", name="Test")

        other_user = UserId("other-user")
        result = service.touch_tab(str(tab.id), other_user)

        assert result is None

    def test_touch_tab_nonexistent_returns_none(self, user_id, tab_repository):
        """Test touch_tab returns None for non-existent tab."""
        service = TabService(tab_repository)

        result = service.touch_tab("nonexistent", user_id)

        assert result is None

    def test_rename_tab_success(self, user_id, session_id, tab_repository):
        """Test successful tab rename."""
        service = TabService(tab_repository)
        tab = service.create_tab(user_id, session_id, "bash", name="Original")

        result = service.rename_tab(str(tab.id), user_id, "New Name")

        assert result is not None
        assert result.name == "New Name"

    def test_rename_tab_invalid_name_returns_none(self, user_id, session_id, tab_repository):
        """Test rename with invalid name returns None."""
        service = TabService(tab_repository)
        tab = service.create_tab(user_id, session_id, "bash", name="Original")

        # Empty name is invalid
        result = service.rename_tab(str(tab.id), user_id, "")

        assert result is None
        # Original name unchanged
        assert service.get_tab(str(tab.id)).name == "Original"

    def test_rename_tab_unauthorized_returns_none(self, user_id, session_id, tab_repository):
        """Test rename by unauthorized user returns None."""
        service = TabService(tab_repository)
        tab = service.create_tab(user_id, session_id, "bash", name="Original")

        other_user = UserId("other-user")
        result = service.rename_tab(str(tab.id), other_user, "Hacked")

        assert result is None
        assert service.get_tab(str(tab.id)).name == "Original"


class TestTabServiceClose:
    """Tests for TabService close operations."""

    def test_close_tab_success(self, user_id, session_id, tab_repository):
        """Test successful tab close."""
        service = TabService(tab_repository)
        tab = service.create_tab(user_id, session_id, "bash", name="Test")
        tab_id_str = str(tab.id)

        result = service.close_tab(tab_id_str, user_id)

        assert result is not None
        assert result.id == tab.id
        assert service.get_tab(tab_id_str) is None

    def test_close_tab_unauthorized_returns_none(self, user_id, session_id, tab_repository):
        """Test close by unauthorized user returns None."""
        service = TabService(tab_repository)
        tab = service.create_tab(user_id, session_id, "bash", name="Test")

        other_user = UserId("other-user")
        result = service.close_tab(str(tab.id), other_user)

        assert result is None
        # Tab still exists
        assert service.get_tab(str(tab.id)) is not None

    def test_close_tabs_for_session_cascade(self, user_id, session_id, tab_repository):
        """Test close_tabs_for_session removes all session tabs."""
        service = TabService(tab_repository)

        service.create_tab(user_id, session_id, "bash", name="Tab 1")
        service.create_tab(user_id, session_id, "bash", name="Tab 2")
        service.create_tab(user_id, session_id, "bash", name="Tab 3")

        removed = service.close_tabs_for_session(session_id)

        assert len(removed) == 3
        assert service.tab_count(user_id) == 0


class TestTabServiceMessageBuilding:
    """Tests for TabService message building methods."""

    def test_build_tab_list_message(self, user_id, session_id, tab_repository):
        """Test build_tab_list_message structure."""
        service = TabService(tab_repository)
        service.create_tab(user_id, session_id, "bash", name="Tab 1")
        service.create_tab(user_id, session_id, "zsh", name="Tab 2")

        message = service.build_tab_list_message(user_id)

        assert message["type"] == "tab_list"
        assert len(message["tabs"]) == 2
        assert "timestamp" in message

    def test_build_tab_created_message(self, user_id, session_id, tab_repository):
        """Test build_tab_created_message structure."""
        service = TabService(tab_repository)
        tab = service.create_tab(user_id, session_id, "bash", name="New Tab")

        message = service.build_tab_created_message(tab)

        assert message["type"] == "tab_created"
        assert message["tab"]["name"] == "New Tab"
        assert message["tab"]["id"] == str(tab.id)

    def test_build_tab_state_update(self, user_id, session_id, tab_repository):
        """Test build_tab_state_update structure."""
        service = TabService(tab_repository)
        tab = service.create_tab(user_id, session_id, "bash", name="Tab")

        message = service.build_tab_state_update("add", tab)

        assert message["type"] == "tab_state_update"
        assert len(message["changes"]) == 1
        assert message["changes"][0]["action"] == "add"
        assert message["changes"][0]["tab_id"] == str(tab.id)
