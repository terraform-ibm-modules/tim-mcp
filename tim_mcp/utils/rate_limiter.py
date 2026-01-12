"""
Rate limiting utilities for Tim MCP.

This module provides rate limiting functionality using a sliding window algorithm
to prevent API abuse and protect upstream services.
"""

import threading
import time
from collections import defaultdict
from functools import wraps
from typing import Any, Callable, Optional

from ..exceptions import RateLimitError
from ..logging import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """
    Thread-safe rate limiter with sliding window algorithm.

    Tracks requests per time window and enforces configurable limits.
    """

    def __init__(self, max_requests: int, window_seconds: int = 60):
        """
        Initialize the rate limiter.

        Args:
            max_requests: Maximum requests allowed in window
            window_seconds: Time window in seconds (default: 60 = 1 minute)
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds

        # Store timestamps of requests: key -> [timestamp1, timestamp2, ...]
        self._requests: defaultdict[str, list[float]] = defaultdict(list)

        # Reentrant lock for thread safety
        self._lock = threading.RLock()

        logger.debug(
            "Rate limiter initialized",
            max_requests=max_requests,
            window_seconds=window_seconds
        )

    def check_limit(self, key: str) -> tuple[bool, Optional[int]]:
        """
        Check if request is allowed under rate limit.

        Uses sliding window algorithm: looks back exactly window_seconds
        from current time to count recent requests.

        Args:
            key: Identifier (e.g., "global" or IP address)

        Returns:
            Tuple of (allowed: bool, reset_time: Optional[int])
            reset_time is Unix timestamp when limit resets (None if allowed)
        """
        with self._lock:
            current_time = time.time()
            cutoff_time = current_time - self.window_seconds

            # Remove old timestamps outside the window (sliding window)
            self._requests[key] = [
                ts for ts in self._requests[key] if ts > cutoff_time
            ]

            # Check if under limit
            request_count = len(self._requests[key])

            if request_count >= self.max_requests:
                # Calculate reset time (when oldest request expires)
                oldest_timestamp = min(self._requests[key])
                reset_time = int(oldest_timestamp + self.window_seconds)

                logger.debug(
                    "Rate limit check: denied",
                    key=key,
                    request_count=request_count,
                    max_requests=self.max_requests,
                    reset_time=reset_time
                )

                return False, reset_time

            logger.debug(
                "Rate limit check: allowed",
                key=key,
                request_count=request_count,
                max_requests=self.max_requests
            )

            return True, None

    def record_request(self, key: str) -> None:
        """
        Record a request timestamp.

        Args:
            key: Identifier (e.g., "global" or IP address)
        """
        with self._lock:
            self._requests[key].append(time.time())
            logger.debug("Recorded request", key=key)

    def get_stats(self, key: str) -> dict[str, Any]:
        """
        Get rate limit statistics for a key.

        Args:
            key: Identifier (e.g., "global" or IP address)

        Returns:
            Dictionary with rate limit statistics:
            - limit: Maximum requests allowed
            - remaining: Requests remaining in window
            - used: Requests used in current window
            - reset_time: Unix timestamp when window resets (None if no requests)
            - window_seconds: Window size in seconds
        """
        with self._lock:
            current_time = time.time()
            cutoff_time = current_time - self.window_seconds

            # Clean old requests
            self._requests[key] = [
                ts for ts in self._requests[key] if ts > cutoff_time
            ]

            request_count = len(self._requests[key])
            remaining = max(0, self.max_requests - request_count)

            reset_time = None
            if self._requests[key]:
                oldest_timestamp = min(self._requests[key])
                reset_time = int(oldest_timestamp + self.window_seconds)

            return {
                "limit": self.max_requests,
                "remaining": remaining,
                "used": request_count,
                "reset_time": reset_time,
                "window_seconds": self.window_seconds
            }


def with_rate_limit(
    global_limiter: Optional[Callable[[], Optional[RateLimiter]]] = None,
    cache: Optional[Callable[..., Any]] = None,
    cache_key_fn: Optional[Callable[..., str]] = None
):
    """
    Decorator to apply rate limiting with cache fallback.

    Checks global rate limit before calling function. If rate limited,
    attempts to serve stale data from cache. Only raises RateLimitError
    if no cache data is available.

    Args:
        global_limiter: Callable that returns global rate limiter instance
                       (lazy evaluation allows module-level usage)
        cache: Callable that returns cache instance (usually lambda self: self.cache)
        cache_key_fn: Function to generate cache key from function args

    Usage:
        @with_rate_limit(
            global_limiter=lambda: _global_limiter,
            cache=lambda self: self.cache,
            cache_key_fn=lambda self, owner, repo: f"repo_info_{owner}_{repo}"
        )
        async def get_data(self, owner: str, repo: str):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get limiter instance (lazy evaluation)
            limiter = global_limiter() if global_limiter else None

            # Skip if no limiter configured
            if limiter is None:
                return await func(*args, **kwargs)

            # Check global rate limit
            allowed, reset_time = limiter.check_limit("global")

            if not allowed:
                logger.warning(
                    "Global rate limit exceeded",
                    reset_time=reset_time,
                    function=func.__name__
                )

                # Try to serve from stale cache
                if cache and cache_key_fn:
                    try:
                        # Cache lambda expects only self (first argument)
                        cache_instance = cache(args[0]) if args else cache()
                        cache_key = cache_key_fn(*args, **kwargs)
                        stale_data = cache_instance.get(cache_key, allow_stale=True)

                        if stale_data is not None:
                            logger.info(
                                "Serving stale cache due to rate limit",
                                cache_key=cache_key,
                                function=func.__name__
                            )
                            return stale_data
                    except Exception as e:
                        logger.warning(
                            "Error accessing cache for stale fallback",
                            error=str(e),
                            function=func.__name__
                        )

                # No cache available, raise error
                raise RateLimitError(
                    "Global rate limit exceeded. Please try again later.",
                    reset_time=reset_time,
                    api_name="TIM-MCP Global"
                )

            # Under limit, record request and proceed
            limiter.record_request("global")

            try:
                return await func(*args, **kwargs)
            except RateLimitError as e:
                # Upstream API rate limited us, try stale cache
                logger.warning(
                    "Upstream API rate limit",
                    upstream_api=e.api_name,
                    function=func.__name__
                )

                if cache and cache_key_fn:
                    try:
                        # Cache lambda expects only self (first argument)
                        cache_instance = cache(args[0]) if args else cache()
                        cache_key = cache_key_fn(*args, **kwargs)
                        stale_data = cache_instance.get(cache_key, allow_stale=True)

                        if stale_data is not None:
                            logger.warning(
                                "Serving stale cache due to upstream rate limit",
                                cache_key=cache_key,
                                upstream_api=e.api_name,
                                function=func.__name__
                            )
                            return stale_data
                    except Exception as cache_error:
                        logger.warning(
                            "Error accessing cache for upstream rate limit fallback",
                            error=str(cache_error),
                            function=func.__name__
                        )

                # Re-raise if no cache
                raise

        return wrapper
    return decorator
