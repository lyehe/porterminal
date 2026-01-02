"""Tests for SessionLimitChecker."""

from datetime import UTC, datetime, timedelta

from porterminal.domain import (
    SessionLimitChecker,
    SessionLimitConfig,
    UserId,
)


class TestSessionLimitChecker:
    """Tests for SessionLimitChecker."""

    def test_can_create_session_under_limits(self, user_id):
        """Test that session can be created under limits."""
        checker = SessionLimitChecker()

        result = checker.can_create_session(
            user_id,
            user_session_count=0,
            total_session_count=0,
        )

        assert result.allowed is True
        assert result.reason is None

    def test_cannot_create_session_at_user_limit(self, user_id):
        """Test that session cannot be created at user limit."""
        checker = SessionLimitChecker(SessionLimitConfig(max_per_user=5))

        result = checker.can_create_session(
            user_id,
            user_session_count=5,
            total_session_count=5,
        )

        assert result.allowed is False
        assert "Maximum sessions" in result.reason

    def test_cannot_create_session_at_total_limit(self, user_id):
        """Test that session cannot be created at total limit."""
        checker = SessionLimitChecker(SessionLimitConfig(max_total=10))

        result = checker.can_create_session(
            user_id,
            user_session_count=1,
            total_session_count=10,
        )

        assert result.allowed is False
        assert "Server session limit" in result.reason

    def test_can_reconnect_own_session(self, sample_session, user_id):
        """Test that user can reconnect to own session."""
        checker = SessionLimitChecker()

        result = checker.can_reconnect(sample_session, user_id)

        assert result.allowed is True

    def test_cannot_reconnect_other_session(self, sample_session):
        """Test that user cannot reconnect to another user's session."""
        checker = SessionLimitChecker()
        other_user = UserId("other-user")

        result = checker.can_reconnect(sample_session, other_user)

        assert result.allowed is False
        assert "another user" in result.reason

    def test_should_cleanup_dead_pty(self, sample_session):
        """Test that session should be cleaned up if PTY is dead."""
        checker = SessionLimitChecker()
        now = datetime.now(UTC)

        should_cleanup, reason = checker.should_cleanup_session(
            sample_session,
            now,
            is_pty_alive=False,
        )

        assert should_cleanup is True
        assert reason == "PTY died"

    def test_should_not_cleanup_alive_session(self, sample_session):
        """Test that alive session should not be cleaned up."""
        checker = SessionLimitChecker()
        now = datetime.now(UTC)

        should_cleanup, reason = checker.should_cleanup_session(
            sample_session,
            now,
            is_pty_alive=True,
        )

        assert should_cleanup is False
        assert reason is None

    def test_should_cleanup_exceeded_max_duration(self, sample_session):
        """Test cleanup for exceeded max duration."""
        checker = SessionLimitChecker(SessionLimitConfig(max_duration_seconds=60))

        # Session is 2 minutes old
        now = sample_session.created_at + timedelta(minutes=2)

        should_cleanup, reason = checker.should_cleanup_session(
            sample_session,
            now,
            is_pty_alive=True,
        )

        assert should_cleanup is True
        assert "max duration" in reason

    def test_should_cleanup_reconnect_window_expired(self, sample_session):
        """Test cleanup for expired reconnection window."""
        checker = SessionLimitChecker(SessionLimitConfig(reconnect_window_seconds=60))
        sample_session.connected_clients = 0  # Disconnect the session

        # Session has been idle for 2 minutes
        now = sample_session.last_activity + timedelta(minutes=2)

        should_cleanup, reason = checker.should_cleanup_session(
            sample_session,
            now,
            is_pty_alive=True,
        )

        assert should_cleanup is True
        assert "Reconnection window" in reason

    def test_connected_session_not_affected_by_reconnect_window(self, sample_session):
        """Test that connected sessions aren't affected by reconnect window."""
        checker = SessionLimitChecker(SessionLimitConfig(reconnect_window_seconds=60))
        # sample_session already has connected_clients=1 from fixture

        # Session has been "idle" for 2 minutes but is still connected
        now = sample_session.last_activity + timedelta(minutes=2)

        should_cleanup, reason = checker.should_cleanup_session(
            sample_session,
            now,
            is_pty_alive=True,
        )

        assert should_cleanup is False

    def test_unlimited_duration_with_zero(self, sample_session):
        """Test that max_duration_seconds=0 means unlimited."""
        checker = SessionLimitChecker(SessionLimitConfig(max_duration_seconds=0))

        # Session is very old
        now = sample_session.created_at + timedelta(days=365)

        should_cleanup, reason = checker.should_cleanup_session(
            sample_session,
            now,
            is_pty_alive=True,
        )

        assert should_cleanup is False

    def test_unlimited_reconnect_with_zero(self, sample_session):
        """Test that reconnect_window_seconds=0 means unlimited."""
        checker = SessionLimitChecker(SessionLimitConfig(reconnect_window_seconds=0))
        sample_session.connected_clients = 0  # Disconnect the session

        # Session has been idle for a very long time
        now = sample_session.last_activity + timedelta(days=365)

        should_cleanup, reason = checker.should_cleanup_session(
            sample_session,
            now,
            is_pty_alive=True,
        )

        assert should_cleanup is False
