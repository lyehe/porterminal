"""Rate limit configuration value object."""

from dataclasses import dataclass

# Defaults: 1KB/s sustained, 16KB burst (allows reasonable paste operations)
DEFAULT_RATE = 1000.0
DEFAULT_BURST = 16384


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
