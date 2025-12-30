"""Rate limit configuration value object."""

from dataclasses import dataclass

# Default business rules
DEFAULT_RATE = 100.0  # tokens per second
DEFAULT_BURST = 500


@dataclass(frozen=True, slots=True)
class RateLimitConfig:
    """Rate limiting configuration (value object)."""

    rate: float = DEFAULT_RATE
    burst: int = DEFAULT_BURST

    def __post_init__(self) -> None:
        if self.rate <= 0:
            raise ValueError("Rate must be positive")
        if self.burst <= 0:
            raise ValueError("Burst must be positive")
