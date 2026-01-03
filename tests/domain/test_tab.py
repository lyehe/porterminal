"""Tests for Tab entity."""

from datetime import UTC, datetime, timedelta

import pytest

from porterminal.domain import Tab


class TestTabCreation:
    """Tests for Tab entity creation and validation."""

    def test_create_tab_valid_name(self, tab_id, user_id, session_id):
        """Test creating a tab with a valid name."""
        now = datetime.now(UTC)
        tab = Tab(
            id=tab_id,
            user_id=user_id,
            session_id=session_id,
            shell_id="bash",
            name="My Terminal",
            created_at=now,
            last_accessed=now,
        )

        assert tab.name == "My Terminal"
        assert tab.shell_id == "bash"

    def test_create_tab_min_length_name(self, tab_id, user_id, session_id):
        """Test creating a tab with minimum length name (1 char)."""
        now = datetime.now(UTC)
        tab = Tab(
            id=tab_id,
            user_id=user_id,
            session_id=session_id,
            shell_id="bash",
            name="X",
            created_at=now,
            last_accessed=now,
        )

        assert tab.name == "X"

    def test_create_tab_max_length_name(self, tab_id, user_id, session_id):
        """Test creating a tab with maximum length name (50 chars)."""
        now = datetime.now(UTC)
        long_name = "A" * 50
        tab = Tab(
            id=tab_id,
            user_id=user_id,
            session_id=session_id,
            shell_id="bash",
            name=long_name,
            created_at=now,
            last_accessed=now,
        )

        assert tab.name == long_name
        assert len(tab.name) == 50

    def test_create_tab_empty_name_raises(self, tab_id, user_id, session_id):
        """Test that empty name raises ValueError."""
        now = datetime.now(UTC)
        with pytest.raises(ValueError, match="1-50 characters"):
            Tab(
                id=tab_id,
                user_id=user_id,
                session_id=session_id,
                shell_id="bash",
                name="",
                created_at=now,
                last_accessed=now,
            )

    def test_create_tab_too_long_name_raises(self, tab_id, user_id, session_id):
        """Test that name over 50 chars raises ValueError."""
        now = datetime.now(UTC)
        long_name = "A" * 51
        with pytest.raises(ValueError, match="1-50 characters"):
            Tab(
                id=tab_id,
                user_id=user_id,
                session_id=session_id,
                shell_id="bash",
                name=long_name,
                created_at=now,
                last_accessed=now,
            )


class TestTabRename:
    """Tests for Tab rename functionality."""

    def test_rename_tab_valid(self, sample_tab):
        """Test renaming a tab with a valid name."""
        sample_tab.rename("New Name")
        assert sample_tab.name == "New Name"

    def test_rename_tab_empty_raises(self, sample_tab):
        """Test that renaming to empty string raises ValueError."""
        with pytest.raises(ValueError, match="1-50 characters"):
            sample_tab.rename("")

    def test_rename_tab_too_long_raises(self, sample_tab):
        """Test that renaming to name over 50 chars raises ValueError."""
        long_name = "B" * 51
        with pytest.raises(ValueError, match="1-50 characters"):
            sample_tab.rename(long_name)


class TestTabTouch:
    """Tests for Tab touch functionality."""

    def test_touch_updates_last_accessed(self, sample_tab):
        """Test that touch updates last_accessed timestamp."""
        original_last_accessed = sample_tab.last_accessed
        new_time = original_last_accessed + timedelta(hours=1)

        sample_tab.touch(new_time)

        assert sample_tab.last_accessed == new_time
        assert sample_tab.last_accessed != original_last_accessed


class TestTabProperties:
    """Tests for Tab properties and serialization."""

    def test_tab_id_property(self, sample_tab):
        """Test tab_id property returns string representation."""
        assert sample_tab.tab_id == str(sample_tab.id)
        assert isinstance(sample_tab.tab_id, str)

    def test_to_dict_serialization(self, sample_tab):
        """Test to_dict returns correct structure."""
        result = sample_tab.to_dict()

        assert result["id"] == str(sample_tab.id)
        assert result["session_id"] == str(sample_tab.session_id)
        assert result["shell_id"] == sample_tab.shell_id
        assert result["name"] == sample_tab.name
        assert "created_at" in result
        assert "last_accessed" in result

    def test_to_dict_datetime_format(self, sample_tab):
        """Test to_dict uses ISO format for datetimes."""
        result = sample_tab.to_dict()

        # Should be parseable ISO format strings
        created_at = result["created_at"]
        last_accessed = result["last_accessed"]

        assert isinstance(created_at, str)
        assert isinstance(last_accessed, str)
        # ISO format should contain 'T' separator
        assert "T" in created_at
        assert "T" in last_accessed
