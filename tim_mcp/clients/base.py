"""
Base client utilities for API clients.

Provides common patterns for rate limiting, caching, retry logic, and error handling
to reduce code duplication across GitHub and Terraform clients.
"""

from collections.abc import Callable
from functools import wraps
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..exceptions import RateLimitError
from ..utils.rate_limiter import with_rate_limit


def check_rate_limit_response(response: httpx.Response, api_name: str) -> None:
    """Check response for rate limiting and raise if limited."""
    if response.status_code == 429:
        reset_time = response.headers.get("X-RateLimit-Reset")
        raise RateLimitError(
            f"{api_name} rate limit exceeded",
            reset_time=int(reset_time) if reset_time else None,
            api_name=api_name,
        )


def make_cache_key(prefix: str) -> Callable[..., str]:
    """
    Create a cache key generator function for a given prefix.

    Args:
        prefix: The prefix for cache keys (e.g., "repo_info", "module_details")

    Returns:
        A function that generates cache keys from method arguments
    """

    def cache_key_fn(_self: Any, *args, **kwargs) -> str:
        key_parts = [str(a) for a in args]
        key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()) if v is not None)
        return f"{prefix}_{'_'.join(key_parts)}"

    return cache_key_fn


def api_method(cache_key_prefix: str | None = None):
    """
    Combined decorator for API methods with rate limiting, caching, and retry.

    This decorator applies:
    1. Rate limiting with cache integration (via @with_rate_limit)
    2. Exponential backoff retry for transient errors (via @retry)

    Args:
        cache_key_prefix: Prefix for cache keys. If None, caching is disabled.

    Usage:
        @api_method(cache_key_prefix="repo_info")
        async def get_repository_info(self, owner: str, repo: str):
            ...
    """

    def decorator(func: Callable) -> Callable:
        # Build the cache key function if prefix provided
        cache_key_fn = make_cache_key(cache_key_prefix) if cache_key_prefix else None

        # Apply retry decorator
        retryable = retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
        )(func)

        # Apply rate limit decorator with caching
        @with_rate_limit(
            limiter_getter=lambda self: getattr(self, "rate_limiter", None),
            cache_getter=lambda self: getattr(self, "cache", None)
            if cache_key_fn
            else None,
            cache_key_fn=cache_key_fn,
        )
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await retryable(*args, **kwargs)

        return wrapper

    return decorator
