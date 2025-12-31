"""Tab limit checking service - pure business logic."""

from dataclasses import dataclass

from ..entities.tab import MAX_TABS_PER_USER, Tab
from ..values.user_id import UserId


@dataclass(frozen=True)
class TabLimitConfig:
    """Tab limit configuration."""

    max_per_user: int = MAX_TABS_PER_USER


@dataclass
class TabLimitResult:
    """Result of tab limit check."""

    allowed: bool
    reason: str | None = None


class TabLimitChecker:
    """Check tab limits (pure business logic)."""

    def __init__(self, config: TabLimitConfig | None = None) -> None:
        self.config = config or TabLimitConfig()

    def can_create_tab(
        self,
        user_id: UserId,
        user_tab_count: int,
    ) -> TabLimitResult:
        """Check if a new tab can be created for user."""
        if user_tab_count >= self.config.max_per_user:
            return TabLimitResult(
                allowed=False,
                reason=f"Maximum tabs ({self.config.max_per_user}) reached",
            )
        return TabLimitResult(allowed=True)

    def can_access_tab(
        self,
        tab: Tab,
        requesting_user: UserId,
    ) -> TabLimitResult:
        """Check if user can access a tab."""
        if tab.user_id != requesting_user:
            return TabLimitResult(
                allowed=False,
                reason="Tab belongs to another user",
            )
        return TabLimitResult(allowed=True)
