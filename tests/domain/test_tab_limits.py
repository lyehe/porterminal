"""Tests for TabLimitChecker service."""

from porterminal.domain import TabLimitChecker, UserId
from porterminal.domain.services.tab_limits import TabLimitConfig


class TestTabLimitChecker:
    """Tests for TabLimitChecker service."""

    def test_can_create_tab_under_limit(self, user_id, tab_limit_checker):
        """Test that tabs can be created when under the limit."""
        result = tab_limit_checker.can_create_tab(user_id, user_tab_count=5)

        assert result.allowed is True
        assert result.reason is None

    def test_can_create_tab_at_limit_rejected(self, user_id, tab_limit_checker):
        """Test that creating tab at limit is rejected."""
        # Default limit is 20
        result = tab_limit_checker.can_create_tab(user_id, user_tab_count=20)

        assert result.allowed is False
        assert "Maximum tabs" in result.reason
        assert "20" in result.reason

    def test_can_create_tab_over_limit_rejected(self, user_id, tab_limit_checker):
        """Test that creating tab over limit is rejected."""
        result = tab_limit_checker.can_create_tab(user_id, user_tab_count=25)

        assert result.allowed is False
        assert result.reason is not None

    def test_can_access_tab_owner_allowed(self, sample_tab, user_id, tab_limit_checker):
        """Test that tab owner can access their tab."""
        result = tab_limit_checker.can_access_tab(sample_tab, user_id)

        assert result.allowed is True
        assert result.reason is None

    def test_can_access_tab_non_owner_denied(self, sample_tab, tab_limit_checker):
        """Test that non-owner cannot access tab."""
        other_user = UserId("other-user")
        result = tab_limit_checker.can_access_tab(sample_tab, other_user)

        assert result.allowed is False
        assert "another user" in result.reason

    def test_custom_max_tabs_limit(self, user_id):
        """Test TabLimitChecker with custom max tabs limit."""
        config = TabLimitConfig(max_per_user=5)
        checker = TabLimitChecker(config)

        # Under limit - allowed
        result = checker.can_create_tab(user_id, user_tab_count=4)
        assert result.allowed is True

        # At limit - rejected
        result = checker.can_create_tab(user_id, user_tab_count=5)
        assert result.allowed is False
        assert "5" in result.reason

    def test_limit_result_allowed_has_no_reason(self, user_id, tab_limit_checker):
        """Test that allowed results have no reason."""
        result = tab_limit_checker.can_create_tab(user_id, user_tab_count=0)

        assert result.allowed is True
        assert result.reason is None

    def test_limit_result_denied_has_reason(self, user_id, tab_limit_checker):
        """Test that denied results always have a reason."""
        result = tab_limit_checker.can_create_tab(user_id, user_tab_count=100)

        assert result.allowed is False
        assert result.reason is not None
        assert len(result.reason) > 0

    def test_default_limit_is_20(self):
        """Test that the default max tabs per user is 20."""
        checker = TabLimitChecker()

        assert checker.config.max_per_user == 20
