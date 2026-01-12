"""In-memory session repository implementation."""

from typing import TypeVar

from porterminal.domain import Session, SessionId, UserId
from porterminal.domain.ports import SessionRepository

PTYHandle = TypeVar("PTYHandle")


class InMemorySessionRepository(SessionRepository[PTYHandle]):
    """In-memory session storage implementing SessionRepository.

    Thread-safe for async usage (dict operations are atomic in CPython).
    """

    def __init__(self) -> None:
        self._sessions: dict[str, Session[PTYHandle]] = {}
        self._user_sessions: dict[str, set[str]] = {}

    def get(self, session_id: SessionId) -> Session[PTYHandle] | None:
        """Get session by ID."""
        return self._sessions.get(str(session_id))

    def get_by_id_str(self, session_id: str) -> Session[PTYHandle] | None:
        """Get session by ID string."""
        return self._sessions.get(session_id)

    def get_by_user(self, user_id: UserId) -> list[Session[PTYHandle]]:
        """Get all sessions for a user."""
        user_str = str(user_id)
        session_ids = self._user_sessions.get(user_str, set())
        return [self._sessions[sid] for sid in session_ids if sid in self._sessions]

    def add(self, session: Session[PTYHandle]) -> None:
        """Add a new session."""
        session_id = str(session.id)
        user_id = str(session.user_id)

        self._sessions[session_id] = session
        self._user_sessions.setdefault(user_id, set()).add(session_id)

    def remove(self, session_id: SessionId) -> Session[PTYHandle] | None:
        """Remove and return a session."""
        session_id_str = str(session_id)
        session = self._sessions.pop(session_id_str, None)

        if session:
            user_id = str(session.user_id)
            if user_id in self._user_sessions:
                self._user_sessions[user_id].discard(session_id_str)
                if not self._user_sessions[user_id]:
                    del self._user_sessions[user_id]

        return session

    def count(self) -> int:
        """Get total session count."""
        return len(self._sessions)

    def count_for_user(self, user_id: UserId) -> int:
        """Get session count for a user."""
        return len(self._user_sessions.get(str(user_id), set()))

    def all_sessions(self) -> list[Session[PTYHandle]]:
        """Get all sessions."""
        return list(self._sessions.values())
