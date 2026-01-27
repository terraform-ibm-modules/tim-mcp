"""
Rate limiting using the 'limits' library with cache integration.

Provides a wrapper around the 'limits' library for moving window rate limiting.
This module adds a decorator that integrates rate limiting with caching:
- Fresh cache lookup (skip rate limit entirely if cached)
- Stale cache fallback when rate limited
- Automatic cache population after successful API calls
"""

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
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    def try_acquire(self, key: str) -> tuple[bool, int | None]:
        """Atomically check and record a request. Returns (acquired, reset_time).

        This method is atomic - it checks if a slot is available and records
        the request in a single operation, avoiding race conditions.
        """
        acquired = self._limiter.hit(self._rate_limit, key)
        if acquired:
            return True, None
        stats = self._limiter.get_window_stats(self._rate_limit, key)
        reset_time = int(stats.reset_time) if stats.reset_time else None
        return False, reset_time


def with_rate_limit(
    limiter_getter: Callable[[], RateLimiter | None] | None = None,
    cache_getter: Callable[..., Any] | None = None,
    cache_key_fn: Callable[..., str] | None = None,
    rate_limit_key: str = "global",
):
    """Decorator for rate limiting with integrated caching.

    This decorator handles the complete caching workflow:
    1. Check fresh cache first (return immediately if hit, no rate limit consumed)
    2. If cache miss, check rate limit
    3. If rate limited, try stale cache fallback
    4. If not rate limited, call the function and cache the result

    Args:
        limiter_getter: Callable that returns a RateLimiter instance (or None to skip)
        cache_getter: Callable that returns a cache instance given the first arg (self)
        cache_key_fn: Callable that generates cache key from function args
        rate_limit_key: Key for rate limiting bucket (default: "global")

    Note: When using this decorator with @retry, place @retry INSIDE (below) this
    decorator so rate limiting is checked before retries are attempted.
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            cache_instance = None
            cache_key = None

            # Try to get cache instance and key
            # Note: args[0] is typically 'self' when decorating methods
            if cache_getter and cache_key_fn:
                try:
                    cache_instance = cache_getter(args[0]) if args else None
                    cache_key = cache_key_fn(*args, **kwargs)
                except Exception as e:
                    logger.warning(
                        "Failed to get cache instance or key: %s", str(e), exc_info=True
                    )

            # Step 1: Check fresh cache first (no rate limit consumed)
            if cache_instance and cache_key:
                cached = cache_instance.get(cache_key, allow_stale=False)
                if cached is not None:
                    return cached

            # Step 2: Check rate limit
            # Note: limiter_getter receives args[0] (self) when decorating methods
            limiter = None
            if limiter_getter:
                try:
                    limiter = limiter_getter(args[0]) if args else limiter_getter()
                except TypeError:
                    # Fallback for standalone functions without self
                    limiter = limiter_getter()
            if limiter:
                acquired, reset_time = limiter.try_acquire(rate_limit_key)

                if not acquired:
                    # Step 3: Rate limited - try stale cache fallback
                    if cache_instance and cache_key:
                        try:
                            stale_data = cache_instance.get(cache_key, allow_stale=True)
                            if stale_data is not None:
                                logger.debug("Serving stale cache for %s", cache_key)
                                return stale_data
                        except Exception as e:
                            logger.warning(
                                "Failed to get stale cache for %s: %s",
                                cache_key,
                                str(e),
                            )
                    raise RateLimitError(
                        "Global rate limit exceeded. Please try again later.",
                        reset_time=reset_time,
                        api_name="TIM-MCP Global",
                    )

            # Step 4: Call the function
            try:
                result = await func(*args, **kwargs)

                # Cache the result
                if cache_instance and cache_key and result is not None:
                    try:
                        cache_instance.set(cache_key, result)
                    except Exception as e:
                        logger.warning(
                            "Failed to cache result for %s: %s", cache_key, str(e)
                        )

                return result

            except RateLimitError:
                # Upstream API rate limited - try stale cache
                if cache_instance and cache_key:
                    try:
                        stale_data = cache_instance.get(cache_key, allow_stale=True)
                        if stale_data is not None:
                            logger.debug(
                                "Serving stale cache after upstream rate limit for %s",
                                cache_key,
                            )
                            return stale_data
                    except Exception as e:
                        logger.warning(
                            "Failed to get stale cache for %s: %s", cache_key, str(e)
                        )
                raise

        return wrapper

    return decorator
