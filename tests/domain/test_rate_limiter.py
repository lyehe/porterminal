"""Tests for TokenBucketRateLimiter."""

from porterminal.domain import RateLimitConfig, TokenBucketRateLimiter


class TestTokenBucketRateLimiter:
    """Tests for TokenBucketRateLimiter."""

    def test_initial_tokens_equal_burst(self, fake_clock):
        """Test that initial tokens equal burst capacity."""
        config = RateLimitConfig(rate=100.0, burst=500)
        limiter = TokenBucketRateLimiter(config, fake_clock)

        assert limiter.available_tokens == 500

    def test_acquire_single_token(self, fake_clock):
        """Test acquiring a single token."""
        config = RateLimitConfig(rate=100.0, burst=500)
        limiter = TokenBucketRateLimiter(config, fake_clock)

        assert limiter.try_acquire(1) is True
        assert limiter.available_tokens == 499

    def test_acquire_multiple_tokens(self, fake_clock):
        """Test acquiring multiple tokens."""
        config = RateLimitConfig(rate=100.0, burst=500)
        limiter = TokenBucketRateLimiter(config, fake_clock)

        assert limiter.try_acquire(100) is True
        assert limiter.available_tokens == 400

    def test_acquire_all_tokens(self, fake_clock):
        """Test acquiring all available tokens."""
        config = RateLimitConfig(rate=100.0, burst=100)
        limiter = TokenBucketRateLimiter(config, fake_clock)

        assert limiter.try_acquire(100) is True
        assert limiter.available_tokens == 0

    def test_acquire_more_than_available(self, fake_clock):
        """Test acquiring more tokens than available."""
        config = RateLimitConfig(rate=100.0, burst=100)
        limiter = TokenBucketRateLimiter(config, fake_clock)

        assert limiter.try_acquire(101) is False
        assert limiter.available_tokens == 100  # No tokens consumed

    def test_tokens_refill_over_time(self, fake_clock):
        """Test that tokens refill over time."""
        config = RateLimitConfig(rate=100.0, burst=100)
        limiter = TokenBucketRateLimiter(config, fake_clock)

        # Use all tokens
        limiter.try_acquire(100)
        assert limiter.available_tokens == 0

        # Advance time by 0.5 seconds (should add 50 tokens)
        fake_clock.advance(0.5)

        # Next acquire will refill first
        assert limiter.try_acquire(1) is True
        assert limiter.available_tokens == 49  # 50 refilled - 1 acquired

    def test_tokens_capped_at_burst(self, fake_clock):
        """Test that tokens don't exceed burst capacity."""
        config = RateLimitConfig(rate=100.0, burst=100)
        limiter = TokenBucketRateLimiter(config, fake_clock)

        # Advance time significantly
        fake_clock.advance(10.0)  # Would add 1000 tokens

        # Try to acquire - should still be capped at burst
        limiter.try_acquire(1)
        assert limiter.available_tokens <= 99  # burst - 1

    def test_rate_limiting_in_action(self, fake_clock):
        """Test rate limiting over multiple requests."""
        config = RateLimitConfig(rate=10.0, burst=20)
        limiter = TokenBucketRateLimiter(config, fake_clock)

        # Rapid requests should eventually be limited
        success_count = 0
        for _ in range(30):
            if limiter.try_acquire(1):
                success_count += 1

        # Should have succeeded for burst amount
        assert success_count == 20

        # After time passes, should succeed again
        fake_clock.advance(1.0)  # Add 10 tokens
        assert limiter.try_acquire(5) is True

    def test_reset(self, fake_clock):
        """Test resetting the rate limiter."""
        config = RateLimitConfig(rate=100.0, burst=100)
        limiter = TokenBucketRateLimiter(config, fake_clock)

        # Use some tokens
        limiter.try_acquire(50)
        assert limiter.available_tokens == 50

        # Reset
        limiter.reset()
        assert limiter.available_tokens == 100
