"""
Rate limiting using the 'limits' library with stale cache integration.

Provides a wrapper around the 'limits' library for moving window rate limiting.
This module adds a decorator that integrates rate limiting with stale cache
fallback, allowing the application to serve expired cached data when rate limits
are exceeded rather than returning errors to users.
"""

from functools import wraps
from typing import Any, Callable, Optional

from limits import parse, storage
from limits.strategies import MovingWindowRateLimiter

from ..exceptions import RateLimitError


class RateLimiter:
    """Thin wrapper around limits library for rate limiting."""

    def __init__(self, max_requests: int, window_seconds: int = 60):
        self._storage = storage.MemoryStorage()
        self._limiter = MovingWindowRateLimiter(self._storage)
        self._rate_limit = parse(f"{max_requests} per {window_seconds} second")
        self.window_seconds = window_seconds

    def check_limit(self, key: str) -> tuple[bool, Optional[int]]:
        """Check if request allowed. Returns (allowed, reset_time)."""
        allowed = self._limiter.test(self._rate_limit, key)
        stats = self._limiter.get_window_stats(self._rate_limit, key)
        reset_time = None if allowed else int(stats.reset_time) if stats.reset_time else None
        return allowed, reset_time

    def record_request(self, key: str) -> None:
        """Record a request."""
        self._limiter.hit(self._rate_limit, key)

    def get_stats(self, key: str) -> dict[str, Any]:
        """Get rate limit statistics."""
        stats = self._limiter.get_window_stats(self._rate_limit, key)
        used = self._rate_limit.amount - stats.remaining
        return {
            "limit": self._rate_limit.amount,
            "remaining": stats.remaining,
            "used": used,
            "reset_time": int(stats.reset_time) if used > 0 and stats.reset_time else None,
            "window_seconds": self.window_seconds
        }


def _get_stale_cache(cache, cache_key_fn, args, kwargs):
    """Helper to retrieve stale cache data."""
    if not (cache and cache_key_fn):
        return None
    try:
        cache_instance = cache(args[0]) if args else cache()
        cache_key = cache_key_fn(*args, **kwargs)
        return cache_instance.get(cache_key, allow_stale=True)
    except Exception:
        return None


def with_rate_limit(
    global_limiter: Optional[Callable[[], Optional[RateLimiter]]] = None,
    cache: Optional[Callable[..., Any]] = None,
    cache_key_fn: Optional[Callable[..., str]] = None
):
    """Decorator for rate limiting with stale cache fallback."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            limiter = global_limiter() if global_limiter else None
            if not limiter:
                return await func(*args, **kwargs)

            allowed, reset_time = limiter.check_limit("global")

            if not allowed:
                stale_data = _get_stale_cache(cache, cache_key_fn, args, kwargs)
                if stale_data is not None:
                    return stale_data
                raise RateLimitError(
                    "Global rate limit exceeded. Please try again later.",
                    reset_time=reset_time,
                    api_name="TIM-MCP Global"
                )

            limiter.record_request("global")

            try:
                return await func(*args, **kwargs)
            except RateLimitError:
                stale_data = _get_stale_cache(cache, cache_key_fn, args, kwargs)
                if stale_data is not None:
                    return stale_data
                raise

        return wrapper
    return decorator
