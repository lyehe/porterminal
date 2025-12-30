"""Tests for InMemorySessionRepository."""

from datetime import UTC, datetime

from porterminal.domain import Session, SessionId, UserId
from porterminal.infrastructure.repositories import InMemorySessionRepository


class TestInMemorySessionRepository:
    """Tests for InMemorySessionRepository."""

    def test_add_and_get(self, sample_session):
        """Test adding and retrieving a session."""
        repo = InMemorySessionRepository()

        repo.add(sample_session)
        retrieved = repo.get(sample_session.id)

        assert retrieved is sample_session

    def test_get_nonexistent_returns_none(self):
        """Test getting non-existent session returns None."""
        repo = InMemorySessionRepository()

        result = repo.get(SessionId("nonexistent"))

        assert result is None

    def test_get_by_id_str(self, sample_session):
        """Test getting session by ID string."""
        repo = InMemorySessionRepository()
        repo.add(sample_session)

        retrieved = repo.get_by_id_str(str(sample_session.id))

        assert retrieved is sample_session

    def test_get_by_user(self, sample_session, user_id, fake_pty, default_dimensions):
        """Test getting sessions by user."""
        repo = InMemorySessionRepository()
        repo.add(sample_session)

        # Add another session for same user
        now = datetime.now(UTC)
        session2 = Session(
            id=SessionId("session-2"),
            user_id=user_id,
            shell_id="bash",
            dimensions=default_dimensions,
            created_at=now,
            last_activity=now,
            pty_handle=fake_pty,
        )
        repo.add(session2)

        user_sessions = repo.get_by_user(user_id)

        assert len(user_sessions) == 2
        assert sample_session in user_sessions
        assert session2 in user_sessions

    def test_get_by_user_empty(self, user_id):
        """Test getting sessions for user with no sessions."""
        repo = InMemorySessionRepository()

        user_sessions = repo.get_by_user(user_id)

        assert user_sessions == []

    def test_remove(self, sample_session):
        """Test removing a session."""
        repo = InMemorySessionRepository()
        repo.add(sample_session)

        removed = repo.remove(sample_session.id)

        assert removed is sample_session
        assert repo.get(sample_session.id) is None

    def test_remove_nonexistent_returns_none(self):
        """Test removing non-existent session returns None."""
        repo = InMemorySessionRepository()

        removed = repo.remove(SessionId("nonexistent"))

        assert removed is None

    def test_count(self, sample_session, user_id, fake_pty, default_dimensions):
        """Test counting sessions."""
        repo = InMemorySessionRepository()

        assert repo.count() == 0

        repo.add(sample_session)
        assert repo.count() == 1

        now = datetime.now(UTC)
        session2 = Session(
            id=SessionId("session-2"),
            user_id=user_id,
            shell_id="bash",
            dimensions=default_dimensions,
            created_at=now,
            last_activity=now,
            pty_handle=fake_pty,
        )
        repo.add(session2)
        assert repo.count() == 2

    def test_count_for_user(self, sample_session, user_id, fake_pty, default_dimensions):
        """Test counting sessions for a user."""
        repo = InMemorySessionRepository()

        assert repo.count_for_user(user_id) == 0

        repo.add(sample_session)
        assert repo.count_for_user(user_id) == 1

        # Add session for different user
        now = datetime.now(UTC)
        other_session = Session(
            id=SessionId("other-session"),
            user_id=UserId("other-user"),
            shell_id="bash",
            dimensions=default_dimensions,
            created_at=now,
            last_activity=now,
            pty_handle=fake_pty,
        )
        repo.add(other_session)

        # Original user still has 1
        assert repo.count_for_user(user_id) == 1
        assert repo.count_for_user(UserId("other-user")) == 1

    def test_all_sessions(self, sample_session, user_id, fake_pty, default_dimensions):
        """Test getting all sessions."""
        repo = InMemorySessionRepository()

        assert repo.all_sessions() == []

        repo.add(sample_session)

        now = datetime.now(UTC)
        session2 = Session(
            id=SessionId("session-2"),
            user_id=UserId("other-user"),
            shell_id="bash",
            dimensions=default_dimensions,
            created_at=now,
            last_activity=now,
            pty_handle=fake_pty,
        )
        repo.add(session2)

        all_sessions = repo.all_sessions()
        assert len(all_sessions) == 2
        assert sample_session in all_sessions
        assert session2 in all_sessions

    def test_remove_updates_user_sessions(self, sample_session, user_id):
        """Test that removing a session updates user session tracking."""
        repo = InMemorySessionRepository()
        repo.add(sample_session)

        assert repo.count_for_user(user_id) == 1

        repo.remove(sample_session.id)

        assert repo.count_for_user(user_id) == 0
