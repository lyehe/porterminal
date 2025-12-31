"""Tab service - tab lifecycle management and synchronization."""

import logging
import uuid
from datetime import UTC, datetime

from porterminal.domain import (
    SessionId,
    Tab,
    TabId,
    TabLimitChecker,
    UserId,
)
from porterminal.domain.ports import TabRepository

logger = logging.getLogger(__name__)


class TabService:
    """Service for managing terminal tabs.

    Handles tab creation, removal, and synchronization.
    Coordinates with SessionService for session management.
    """

    def __init__(
        self,
        repository: TabRepository,
        limit_checker: TabLimitChecker | None = None,
    ) -> None:
        self._repository = repository
        self._limit_checker = limit_checker or TabLimitChecker()

    def create_tab(
        self,
        user_id: UserId,
        session_id: SessionId,
        shell_id: str,
        name: str | None = None,
    ) -> Tab:
        """Create a new tab for a session.

        Args:
            user_id: User creating the tab.
            session_id: Session this tab references.
            shell_id: Shell type identifier.
            name: Optional tab name (generated if not provided).

        Returns:
            Created tab.

        Raises:
            ValueError: If tab limits exceeded or invalid input.
        """
        # Check limits
        user_tab_count = self._repository.count_for_user(user_id)
        limit_result = self._limit_checker.can_create_tab(user_id, user_tab_count)
        if not limit_result.allowed:
            raise ValueError(limit_result.reason)

        # Generate name if not provided
        if not name:
            name = shell_id.capitalize()

        # Create tab
        now = datetime.now(UTC)
        tab = Tab(
            id=TabId(str(uuid.uuid4())),
            user_id=user_id,
            session_id=session_id,
            shell_id=shell_id,
            name=name,
            created_at=now,
            last_accessed=now,
        )

        self._repository.add(tab)
        logger.info(
            "Tab created user_id=%s tab_id=%s session_id=%s",
            user_id,
            tab.id,
            session_id,
        )
        return tab

    def get_tab(self, tab_id: str) -> Tab | None:
        """Get a tab by ID string."""
        return self._repository.get_by_id_str(tab_id)

    def get_user_tabs(self, user_id: UserId) -> list[Tab]:
        """Get all tabs for a user.

        Returns:
            List of tabs ordered by created_at ASC.
        """
        return self._repository.get_by_user(user_id)

    def get_tabs_for_session(self, session_id: SessionId) -> list[Tab]:
        """Get all tabs referencing a session."""
        return self._repository.get_by_session(session_id)

    def touch_tab(self, tab_id: str, user_id: UserId) -> Tab | None:
        """Update tab's last accessed time.

        Args:
            tab_id: Tab to touch.
            user_id: Requesting user (for authorization).

        Returns:
            Updated tab or None if not found/unauthorized.
        """
        tab = self._repository.get_by_id_str(tab_id)
        if not tab:
            return None

        # Check ownership
        limit_result = self._limit_checker.can_access_tab(tab, user_id)
        if not limit_result.allowed:
            logger.warning(
                "Tab access denied tab_id=%s user_id=%s reason=%s",
                tab_id,
                user_id,
                limit_result.reason,
            )
            return None

        tab.touch(datetime.now(UTC))
        self._repository.update(tab)
        return tab

    def rename_tab(self, tab_id: str, user_id: UserId, new_name: str) -> Tab | None:
        """Rename a tab.

        Args:
            tab_id: Tab to rename.
            user_id: Requesting user (for authorization).
            new_name: New name for the tab.

        Returns:
            Updated tab or None if not found/unauthorized.
        """
        tab = self._repository.get_by_id_str(tab_id)
        if not tab:
            return None

        # Check ownership
        limit_result = self._limit_checker.can_access_tab(tab, user_id)
        if not limit_result.allowed:
            return None

        try:
            tab.rename(new_name)
            self._repository.update(tab)
            logger.info("Tab renamed tab_id=%s new_name=%s", tab_id, new_name)
            return tab
        except ValueError as e:
            logger.warning("Tab rename failed tab_id=%s error=%s", tab_id, e)
            return None

    def close_tab(self, tab_id: str, user_id: UserId) -> Tab | None:
        """Close a tab.

        Args:
            tab_id: Tab to close.
            user_id: Requesting user (for authorization).

        Returns:
            Removed tab or None if not found/unauthorized.
        """
        tab = self._repository.get_by_id_str(tab_id)
        if not tab:
            return None

        # Check ownership
        limit_result = self._limit_checker.can_access_tab(tab, user_id)
        if not limit_result.allowed:
            return None

        removed = self._repository.remove(tab.id)
        if removed:
            logger.info(
                "Tab closed user_id=%s tab_id=%s session_id=%s",
                user_id,
                tab_id,
                removed.session_id,
            )
        return removed

    def close_tabs_for_session(self, session_id: SessionId) -> list[Tab]:
        """Close all tabs referencing a session (cascade).

        Called when a session is destroyed.

        Returns:
            List of removed tabs.
        """
        removed = self._repository.remove_by_session(session_id)
        if removed:
            logger.info(
                "Tabs closed for session session_id=%s count=%d",
                session_id,
                len(removed),
            )
        return removed

    def tab_count(self, user_id: UserId | None = None) -> int:
        """Get tab count.

        Args:
            user_id: If provided, count for this user only.

        Returns:
            Tab count.
        """
        if user_id:
            return self._repository.count_for_user(user_id)
        return self._repository.count()

    def build_tab_list_message(self, user_id: UserId) -> dict:
        """Build a tab_list message for a user.

        Returns:
            Message dict ready for WebSocket send.
        """
        tabs = self.get_user_tabs(user_id)
        return {
            "type": "tab_list",
            "tabs": [tab.to_dict() for tab in tabs],
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def build_tab_created_message(self, tab: Tab) -> dict:
        """Build a tab_created message for broadcasting.

        Returns:
            Message dict ready for WebSocket send.
        """
        return {
            "type": "tab_created",
            "tab": tab.to_dict(),
        }

    def build_tab_closed_message(self, tab_id: str, reason: str = "user") -> dict:
        """Build a tab_closed message for broadcasting.

        Returns:
            Message dict ready for WebSocket send.
        """
        return {
            "type": "tab_closed",
            "tab_id": tab_id,
            "reason": reason,
        }

    def build_tab_state_sync(self, user_id: UserId) -> dict:
        """Build full state sync message for a user.

        Returns:
            Message dict with all tabs for the user.
        """
        tabs = self.get_user_tabs(user_id)
        return {
            "type": "tab_state_sync",
            "tabs": [tab.to_dict() for tab in tabs],
        }

    def build_tab_state_update(self, action: str, tab: Tab, reason: str | None = None) -> dict:
        """Build incremental state update message.

        Args:
            action: One of 'add', 'remove', 'update'.
            tab: Tab that changed.
            reason: Optional reason (for 'remove' action).

        Returns:
            Message dict with the state change.
        """
        change: dict = {"action": action, "tab_id": tab.tab_id}
        if action in ("add", "update"):
            change["tab"] = tab.to_dict()
        if reason:
            change["reason"] = reason
        return {
            "type": "tab_state_update",
            "changes": [change],
        }
