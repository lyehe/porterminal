"""Pure token bucket rate limiter - synchronous, no asyncio dependency."""

from dataclasses import dataclass, field
from typing import Protocol

from ..values.rate_limit_config import RateLimitConfig


class Clock(Protocol):
    """Protocol for time source (dependency injection)."""

    def now(self) -> float:
        """Return current time in seconds (monotonic)."""
        ...


@dataclass
class TokenBucketRateLimiter:
    """Pure token bucket rate limiter.

    Synchronous, no asyncio dependency.
    Time source is injected for testability.
    """

    config: RateLimitConfig
    clock: Clock
    _tokens: float = field(init=False)
    _last_update: float = field(init=False)

    def __post_init__(self) -> None:
        self._tokens = float(self.config.burst)
        self._last_update = self.clock.now()

    def try_acquire(self, tokens: int = 1) -> bool:
        """Try to acquire tokens.

        Args:
            tokens: Number of tokens to acquire.

        Returns:
            True if tokens were acquired, False if rate limited.
        """
        now = self.clock.now()
        elapsed = now - self._last_update

        # Refill bucket
        self._tokens = min(self.config.burst, self._tokens + elapsed * self.config.rate)
        self._last_update = now

        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False

    @property
    def available_tokens(self) -> float:
        """Get current available tokens (for monitoring)."""
        return self._tokens

    def reset(self) -> None:
        """Reset the rate limiter to full capacity."""
        self._tokens = float(self.config.burst)
        self._last_update = self.clock.now()
