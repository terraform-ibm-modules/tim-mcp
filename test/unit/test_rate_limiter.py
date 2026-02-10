"""Unit tests for RateLimiter."""

import threading
import time

import pytest

from tim_mcp.exceptions import RateLimitError
from tim_mcp.utils.rate_limiter import RateLimiter


class TestRateLimiter:
    """Test suite for RateLimiter class."""

    def test_try_acquire_allows_under_limit(self):
        """Test that requests are allowed when under limit."""
        limiter = RateLimiter(max_requests=5, window_seconds=60)

        # Make 5 requests (at limit)
        for i in range(5):
            acquired, reset_time = limiter.try_acquire("test_key")
            assert acquired is True
            assert reset_time is None

    def test_try_acquire_blocks_over_limit(self):
        """Test that requests are blocked when over limit."""
        limiter = RateLimiter(max_requests=2, window_seconds=60)

        # Make 2 requests (at limit)
        limiter.try_acquire("test_key")
        limiter.try_acquire("test_key")

        # Third request should be blocked
        acquired, reset_time = limiter.try_acquire("test_key")
        assert acquired is False
        assert reset_time is not None
        assert isinstance(reset_time, int)

    def test_rate_limiter_sliding_window(self):
        """Test that sliding window expires old requests.

        Note: Using real sleep here as the limits library uses internal time tracking
        that doesn't work well with freezegun. This is acceptable for a single test
        validating time-based expiration behavior.
        """
        limiter = RateLimiter(max_requests=2, window_seconds=1)

        # Make 2 requests (at limit)
        limiter.try_acquire("test_key")
        limiter.try_acquire("test_key")

        # Should be blocked
        acquired, _ = limiter.try_acquire("test_key")
        assert acquired is False

        # Wait for window to expire (limits library requires real time)
        time.sleep(1.1)

        # Should be allowed again
        acquired, reset_time = limiter.try_acquire("test_key")
        assert acquired is True
        assert reset_time is None

    def test_rate_limiter_per_key_isolation(self):
        """Test that different keys have independent limits."""
        limiter = RateLimiter(max_requests=1, window_seconds=60)

        # Use up limit for key1
        limiter.try_acquire("key1")

        # key1 should be limited
        acquired, _ = limiter.try_acquire("key1")
        assert acquired is False

        # key2 should still be allowed
        acquired, _ = limiter.try_acquire("key2")
        assert acquired is True

    def test_rate_limiter_thread_safety(self):
        """Test that rate limiter is thread-safe."""
        limiter = RateLimiter(max_requests=100, window_seconds=60)
        errors = []
        acquired_count = [0]
        lock = threading.Lock()

        def make_requests(count):
            """Make rate limit requests."""
            try:
                for _ in range(count):
                    acquired, _ = limiter.try_acquire("test_key")
                    if acquired:
                        with lock:
                            acquired_count[0] += 1
            except Exception as e:
                errors.append(e)

        # Create multiple threads
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=make_requests, args=(30,))
            threads.append(thread)

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # No errors should have occurred
        assert len(errors) == 0

        # Should have exactly 100 successful acquires
        assert acquired_count[0] == 100

    def test_rate_limiter_multiple_keys(self):
        """Test managing multiple keys simultaneously."""
        limiter = RateLimiter(max_requests=2, window_seconds=60)

        # Use different keys
        limiter.try_acquire("key1")
        limiter.try_acquire("key2")
        limiter.try_acquire("key3")

        # Each should allow one more
        assert limiter.try_acquire("key1")[0] is True
        assert limiter.try_acquire("key2")[0] is True
        assert limiter.try_acquire("key3")[0] is True

    def test_rate_limiter_exact_limit_boundary(self):
        """Test behavior exactly at the limit boundary."""
        limiter = RateLimiter(max_requests=3, window_seconds=60)

        # Make exactly 3 requests
        for _ in range(3):
            acquired, _ = limiter.try_acquire("test_key")
            assert acquired is True

        # Next acquire should fail
        acquired, reset_time = limiter.try_acquire("test_key")
        assert acquired is False
        assert reset_time is not None


@pytest.mark.asyncio
class TestRateLimitDecorator:
    """Test suite for with_rate_limit decorator."""

    async def test_decorator_without_limiter(self):
        """Test decorator passes through when no limiter configured."""
        from tim_mcp.utils.rate_limiter import with_rate_limit

        @with_rate_limit(limiter_getter=None)
        async def test_func():
            return "success"

        result = await test_func()
        assert result == "success"

    async def test_decorator_with_limiter_under_limit(self):
        """Test decorator allows requests when under limit."""
        from tim_mcp.utils.rate_limiter import with_rate_limit

        limiter = RateLimiter(max_requests=5, window_seconds=60)

        @with_rate_limit(limiter_getter=lambda: limiter)
        async def test_func():
            return "success"

        # Should succeed 5 times
        for _ in range(5):
            result = await test_func()
            assert result == "success"

    async def test_decorator_blocks_over_limit(self):
        """Test decorator blocks requests when over limit."""
        from tim_mcp.utils.rate_limiter import with_rate_limit

        limiter = RateLimiter(max_requests=1, window_seconds=60)

        @with_rate_limit(limiter_getter=lambda: limiter)
        async def test_func():
            return "success"

        # First should succeed
        result = await test_func()
        assert result == "success"

        # Second should raise RateLimitError
        with pytest.raises(RateLimitError) as exc_info:
            await test_func()

        assert "Rate limit exceeded" in str(exc_info.value)

    async def test_decorator_serves_stale_cache(self):
        """Test decorator serves stale cache when rate limited.

        Note: Cache TTL uses time.monotonic() internally, requiring real sleep
        for accurate expiration testing.
        """
        from tim_mcp.utils.cache import InMemoryCache
        from tim_mcp.utils.rate_limiter import with_rate_limit

        # Use 0 rate limit slots to immediately trigger rate limiting
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        cache = InMemoryCache(fresh_ttl=1, evict_ttl=10, maxsize=10)

        # Pre-populate cache with stale data
        cache.set("test_key", "stale_value")
        time.sleep(1.1)  # Wait for primary cache expiration (stale cache retains it)

        # Exhaust the rate limit before calling the decorated function
        limiter.try_acquire("global")

        call_count = 0

        class Wrapper:
            """Wrapper class to simulate method with self."""

            @with_rate_limit(
                limiter_getter=lambda self: limiter,
                cache_getter=lambda self: cache,
                cache_key_fn=lambda self: "test_key",
            )
            async def test_func(self):
                nonlocal call_count
                call_count += 1
                return "fresh_value"

        wrapper = Wrapper()

        # Call should be rate limited but serve stale cache
        result = await wrapper.test_func()
        assert result == "stale_value"
        assert call_count == 0  # Function never called due to rate limit

    async def test_decorator_caches_fresh_results(self):
        """Test decorator caches fresh results after successful calls."""
        from tim_mcp.utils.cache import InMemoryCache
        from tim_mcp.utils.rate_limiter import with_rate_limit

        limiter = RateLimiter(max_requests=10, window_seconds=60)
        cache = InMemoryCache(fresh_ttl=3600, maxsize=10)

        call_count = 0

        class Wrapper:
            """Wrapper class to simulate method with self."""

            @with_rate_limit(
                limiter_getter=lambda self: limiter,
                cache_getter=lambda self: cache,
                cache_key_fn=lambda self: "test_key",
            )
            async def test_func(self):
                nonlocal call_count
                call_count += 1
                return "fresh_value"

        wrapper = Wrapper()

        # First call should execute function and cache result
        result = await wrapper.test_func()
        assert result == "fresh_value"
        assert call_count == 1

        # Second call should return cached result without executing function
        result = await wrapper.test_func()
        assert result == "fresh_value"
        assert call_count == 1  # Still 1, function not called again

    async def test_decorator_with_cache_getter_receiving_self(self):
        """Test decorator properly passes self to cache_getter."""
        from tim_mcp.utils.cache import InMemoryCache
        from tim_mcp.utils.rate_limiter import with_rate_limit

        class MockClient:
            def __init__(self):
                self.cache = InMemoryCache(fresh_ttl=3600, maxsize=10)
                self.rate_limiter = RateLimiter(max_requests=10, window_seconds=60)

            @with_rate_limit(
                limiter_getter=lambda self: self.rate_limiter,
                cache_getter=lambda self: self.cache,
                cache_key_fn=lambda self, arg: f"key_{arg}",
            )
            async def fetch_data(self, arg: str):
                return f"data_{arg}"

        client = MockClient()

        # First call caches result
        result = await client.fetch_data("test")
        assert result == "data_test"

        # Verify it's cached
        assert client.cache.get("key_test") == "data_test"
