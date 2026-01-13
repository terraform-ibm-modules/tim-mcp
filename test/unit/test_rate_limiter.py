"""Unit tests for RateLimiter."""

import pytest
import time
import threading
from tim_mcp.utils.rate_limiter import RateLimiter
from tim_mcp.exceptions import RateLimitError


class TestRateLimiter:
    """Test suite for RateLimiter class."""

    def test_rate_limiter_allows_under_limit(self):
        """Test that requests are allowed when under limit."""
        limiter = RateLimiter(max_requests=5, window_seconds=60)

        # Make 5 requests (at limit)
        for i in range(5):
            allowed, reset_time = limiter.check_limit("test_key")
            assert allowed is True
            assert reset_time is None
            limiter.record_request("test_key")

    def test_rate_limiter_blocks_over_limit(self):
        """Test that requests are blocked when over limit."""
        limiter = RateLimiter(max_requests=2, window_seconds=60)

        # Make 2 requests (at limit)
        limiter.record_request("test_key")
        limiter.record_request("test_key")

        # Third request should be blocked
        allowed, reset_time = limiter.check_limit("test_key")
        assert allowed is False
        assert reset_time is not None
        assert isinstance(reset_time, int)

    def test_rate_limiter_sliding_window(self):
        """Test that sliding window expires old requests."""
        limiter = RateLimiter(max_requests=2, window_seconds=1)

        # Make 2 requests (at limit)
        limiter.record_request("test_key")
        limiter.record_request("test_key")

        # Should be blocked
        allowed, _ = limiter.check_limit("test_key")
        assert allowed is False

        # Wait for window to expire
        time.sleep(1.1)

        # Should be allowed again
        allowed, reset_time = limiter.check_limit("test_key")
        assert allowed is True
        assert reset_time is None

    def test_rate_limiter_per_key_isolation(self):
        """Test that different keys have independent limits."""
        limiter = RateLimiter(max_requests=1, window_seconds=60)

        # Use up limit for key1
        limiter.record_request("key1")

        # key1 should be limited
        allowed, _ = limiter.check_limit("key1")
        assert allowed is False

        # key2 should still be allowed
        allowed, _ = limiter.check_limit("key2")
        assert allowed is True

    def test_rate_limiter_stats(self):
        """Test rate limiter statistics."""
        limiter = RateLimiter(max_requests=5, window_seconds=60)

        # Empty stats
        stats = limiter.get_stats("test_key")
        assert stats["limit"] == 5
        assert stats["remaining"] == 5
        assert stats["used"] == 0
        assert stats["reset_time"] is None
        assert stats["window_seconds"] == 60

        # After some requests
        limiter.record_request("test_key")
        limiter.record_request("test_key")

        stats = limiter.get_stats("test_key")
        assert stats["remaining"] == 3
        assert stats["used"] == 2
        assert stats["reset_time"] is not None

    def test_rate_limiter_reset_time_calculation(self):
        """Test that reset time is calculated correctly."""
        limiter = RateLimiter(max_requests=1, window_seconds=10)

        # Record a request
        before = time.time()
        limiter.record_request("test_key")
        after = time.time()

        # Check limit
        allowed, reset_time = limiter.check_limit("test_key")
        assert allowed is False
        assert reset_time is not None

        # Reset time should be approximately 10 seconds from now
        expected_reset = before + 10
        assert abs(reset_time - expected_reset) < 1  # Within 1 second tolerance

    def test_rate_limiter_thread_safety(self):
        """Test that rate limiter is thread-safe."""
        limiter = RateLimiter(max_requests=100, window_seconds=60)
        errors = []

        def make_requests(count):
            """Make rate limit requests."""
            try:
                for i in range(count):
                    allowed, _ = limiter.check_limit("test_key")
                    if allowed:
                        limiter.record_request("test_key")
            except Exception as e:
                errors.append(e)

        # Create multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=make_requests, args=(20,))
            threads.append(thread)

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # No errors should have occurred
        assert len(errors) == 0

        # Should have 100 requests recorded
        stats = limiter.get_stats("test_key")
        assert stats["used"] == 100

    def test_rate_limiter_cleanup_old_timestamps(self):
        """Test that old timestamps are cleaned up."""
        limiter = RateLimiter(max_requests=5, window_seconds=1)

        # Make some requests
        for i in range(3):
            limiter.record_request("test_key")

        # Check that requests are tracked
        stats = limiter.get_stats("test_key")
        assert stats["used"] == 3

        # Wait for window to expire
        time.sleep(1.1)

        # Get stats (should trigger cleanup)
        stats = limiter.get_stats("test_key")
        assert stats["used"] == 0  # Old requests cleaned up

    def test_rate_limiter_multiple_keys(self):
        """Test managing multiple keys simultaneously."""
        limiter = RateLimiter(max_requests=2, window_seconds=60)

        # Use different keys
        limiter.record_request("key1")
        limiter.record_request("key2")
        limiter.record_request("key3")

        # Each should have 1 request
        assert limiter.get_stats("key1")["used"] == 1
        assert limiter.get_stats("key2")["used"] == 1
        assert limiter.get_stats("key3")["used"] == 1

        # Each should allow one more
        assert limiter.check_limit("key1")[0] is True
        assert limiter.check_limit("key2")[0] is True
        assert limiter.check_limit("key3")[0] is True

    def test_rate_limiter_exact_limit_boundary(self):
        """Test behavior exactly at the limit boundary."""
        limiter = RateLimiter(max_requests=3, window_seconds=60)

        # Make exactly 3 requests
        for i in range(3):
            allowed, _ = limiter.check_limit("test_key")
            assert allowed is True
            limiter.record_request("test_key")

        # Next check should fail
        allowed, reset_time = limiter.check_limit("test_key")
        assert allowed is False
        assert reset_time is not None

    def test_rate_limiter_zero_requests(self):
        """Test stats with zero requests."""
        limiter = RateLimiter(max_requests=10, window_seconds=60)

        stats = limiter.get_stats("never_used_key")
        assert stats["used"] == 0
        assert stats["remaining"] == 10
        assert stats["reset_time"] is None


@pytest.mark.asyncio
class TestRateLimitDecorator:
    """Test suite for with_rate_limit decorator."""

    async def test_decorator_without_limiter(self):
        """Test decorator passes through when no limiter configured."""
        from tim_mcp.utils.rate_limiter import with_rate_limit

        @with_rate_limit(global_limiter=None)
        async def test_func():
            return "success"

        result = await test_func()
        assert result == "success"

    async def test_decorator_with_limiter_under_limit(self):
        """Test decorator allows requests when under limit."""
        from tim_mcp.utils.rate_limiter import with_rate_limit

        limiter = RateLimiter(max_requests=5, window_seconds=60)

        @with_rate_limit(global_limiter=lambda: limiter)
        async def test_func():
            return "success"

        # Should succeed 5 times
        for i in range(5):
            result = await test_func()
            assert result == "success"

    async def test_decorator_blocks_over_limit(self):
        """Test decorator blocks requests when over limit."""
        from tim_mcp.utils.rate_limiter import with_rate_limit

        limiter = RateLimiter(max_requests=1, window_seconds=60)

        @with_rate_limit(global_limiter=lambda: limiter)
        async def test_func():
            return "success"

        # First should succeed
        result = await test_func()
        assert result == "success"

        # Second should raise RateLimitError
        with pytest.raises(RateLimitError) as exc_info:
            await test_func()

        assert "Global rate limit exceeded" in str(exc_info.value)

    async def test_decorator_serves_stale_cache(self):
        """Test decorator serves stale cache when rate limited."""
        from tim_mcp.utils.rate_limiter import with_rate_limit
        from tim_mcp.utils.cache import InMemoryCache

        limiter = RateLimiter(max_requests=1, window_seconds=60)
        cache = InMemoryCache(ttl=1, maxsize=10)

        # Pre-populate cache with stale data
        cache.set("test_key", "stale_value")
        time.sleep(1.1)  # Wait for expiration

        call_count = 0

        @with_rate_limit(
            global_limiter=lambda: limiter,
            cache=lambda: cache,
            cache_key_fn=lambda: "test_key"
        )
        async def test_func():
            nonlocal call_count
            call_count += 1
            return "fresh_value"

        # First call should execute function
        result = await test_func()
        assert result == "fresh_value"
        assert call_count == 1

        # Second call should be rate limited but serve stale cache
        result = await test_func()
        assert result == "stale_value"
        assert call_count == 1  # Function not called again
