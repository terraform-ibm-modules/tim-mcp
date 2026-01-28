"""Rate limiting with cache integration using the 'limits' library."""

import logging
from collections.abc import Callable
from functools import wraps
from typing import Any

from limits import parse, storage
from limits.strategies import MovingWindowRateLimiter

from ..exceptions import RateLimitError

logger = logging.getLogger(__name__)


class RateLimiter:
    """Thin wrapper around limits library for rate limiting."""

    def __init__(self, max_requests: int, window_seconds: int = 60):
        self._storage = storage.MemoryStorage()
        self._limiter = MovingWindowRateLimiter(self._storage)
        self._rate_limit = parse(f"{max_requests} per {window_seconds} second")

    def try_acquire(self, key: str) -> tuple[bool, int | None]:
        """Atomically check and record a request. Returns (acquired, reset_time)."""
        if self._limiter.hit(self._rate_limit, key):
            return True, None
        stats = self._limiter.get_window_stats(self._rate_limit, key)
        return False, int(stats.reset_time) if stats.reset_time else None


def with_rate_limit(
    limiter_getter: Callable[..., RateLimiter | None] | None = None,
    cache_getter: Callable[..., Any] | None = None,
    cache_key_fn: Callable[..., str] | None = None,
    rate_limit_key: str = "global",
):
    """Decorator for rate limiting with integrated caching.

    Workflow:
    1. Check fresh cache first (return immediately if hit, no rate limit consumed)
    2. If cache miss, check rate limit
    3. If rate limited, try stale cache fallback
    4. If not rate limited, call the function and cache the result
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get cache instance and key
            cache = None
            cache_key = None
            if cache_getter and cache_key_fn and args:
                try:
                    cache = cache_getter(args[0])
                    cache_key = cache_key_fn(*args, **kwargs)
                except Exception:
                    pass

            def try_stale_cache():
                if cache and cache_key:
                    try:
                        return cache.get(cache_key, allow_stale=True)
                    except Exception:
                        pass
                return None

            # Step 1: Check fresh cache
            if cache and cache_key:
                cached = cache.get(cache_key, allow_stale=False)
                if cached is not None:
                    return cached

            # Step 2: Check rate limit
            if limiter_getter:
                try:
                    limiter = limiter_getter(args[0]) if args else limiter_getter()
                except TypeError:
                    limiter = limiter_getter()
                if limiter:
                    acquired, reset_time = limiter.try_acquire(rate_limit_key)
                    if not acquired:
                        stale = try_stale_cache()
                        if stale is not None:
                            return stale
                        raise RateLimitError(
                            "Rate limit exceeded. Please try again later.",
                            reset_time=reset_time,
                        )

            # Step 3: Call the function
            try:
                result = await func(*args, **kwargs)
                if cache and cache_key and result is not None:
                    cache.set(cache_key, result)
                return result
            except RateLimitError:
                stale = try_stale_cache()
                if stale is not None:
                    return stale
                raise

        return wrapper

    return decorator
