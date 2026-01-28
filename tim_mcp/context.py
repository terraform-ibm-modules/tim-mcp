"""
Shared application context for TIM-MCP.

This module holds shared instances (rate limiter, cache) that are initialized
at server startup and can be imported by tools without circular import issues.
"""

from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from .utils.cache import InMemoryCache
    from .utils.rate_limiter import RateLimiter
    from .utils.tiered_cache import AsyncTieredCache

# Type alias for cache implementations
CacheType = Union["InMemoryCache", "AsyncTieredCache"]

# Global instances initialized at server startup
_rate_limiter: "RateLimiter | None" = None
_cache: "CacheType | None" = None


def init_context(rate_limiter: "RateLimiter", cache: "CacheType") -> None:
    """
    Initialize the shared context with rate limiter and cache.

    Called once at server startup.

    Args:
        rate_limiter: Global rate limiter instance
        cache: Shared cache instance (InMemoryCache or AsyncTieredCache)
    """
    global _rate_limiter, _cache
    _rate_limiter = rate_limiter
    _cache = cache


def get_rate_limiter() -> "RateLimiter | None":
    """Get the global rate limiter instance."""
    return _rate_limiter


def get_cache() -> "CacheType | None":
    """Get the shared cache instance."""
    return _cache
