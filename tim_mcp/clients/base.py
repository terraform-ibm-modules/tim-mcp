"""
Base client utilities for API clients.

Provides common patterns for rate limiting, caching, retry logic, and error handling
to reduce code duplication across GitHub and Terraform clients.
"""

import time
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
from ..logging import get_logger, log_api_request
from ..utils.cache import InMemoryCache
from ..utils.rate_limiter import RateLimiter, with_rate_limit

logger = get_logger(__name__)


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
            cache_getter=lambda self: getattr(self, "cache", None) if cache_key_fn else None,
            cache_key_fn=cache_key_fn,
        )
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await retryable(*args, **kwargs)

        return wrapper

    return decorator


class BaseAPIClient:
    """Base class for API clients with common functionality."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        cache: InMemoryCache | None = None,
        rate_limiter: RateLimiter | None = None,
        api_name: str = "API",
    ):
        """
        Initialize the base client.

        Args:
            client: The httpx async client
            cache: Optional cache instance
            rate_limiter: Optional rate limiter instance
            api_name: Name of the API for logging/errors
        """
        self.client = client
        self.cache = cache
        self.rate_limiter = rate_limiter
        self.api_name = api_name
        self.logger = get_logger(__name__, client=api_name.lower())

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.client.aclose()

    def _handle_rate_limit_response(self, response: httpx.Response) -> None:
        """
        Check response for rate limiting and raise if limited.

        Args:
            response: The HTTP response to check

        Raises:
            RateLimitError: If the response indicates rate limiting (429)
        """
        if response.status_code == 429:
            reset_time = response.headers.get("X-RateLimit-Reset")
            raise RateLimitError(
                f"{self.api_name} rate limit exceeded",
                reset_time=int(reset_time) if reset_time else None,
                api_name=self.api_name,
            )

    async def _request(
        self,
        method: str,
        url: str,
        params: dict | None = None,
        **log_context,
    ) -> httpx.Response:
        """
        Make an HTTP request with logging and rate limit handling.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            params: Optional query parameters
            **log_context: Additional context for logging

        Returns:
            The HTTP response

        Raises:
            RateLimitError: If rate limited
            httpx.HTTPStatusError: If the response has an error status
        """
        start_time = time.time()

        response = await self.client.request(method, url, params=params)
        duration_ms = (time.time() - start_time) * 1000

        self._handle_rate_limit_response(response)

        log_api_request(
            self.logger,
            method,
            str(response.url),
            response.status_code,
            duration_ms,
            **log_context,
        )

        return response
