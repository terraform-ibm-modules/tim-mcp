"""
Shared application context for TIM-MCP.

This module holds shared instances (rate limiter, cache) that are initialized
at server startup and can be imported by tools without circular import issues.
"""

from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from .utils.cache import InMemoryCache
    from .utils.rate_limiter import RateLimiter
    from .utils.redis_cache import RedisCache
    from .utils.tiered_cache import AsyncTieredCache

# Type alias for cache implementations
CacheType = Union["InMemoryCache", "AsyncTieredCache"]

# Global instances initialized at server startup
_rate_limiter: "RateLimiter | None" = None
_cache: "CacheType | None" = None
_redis_cache: "RedisCache | None" = None


def init_context(
    rate_limiter: "RateLimiter",
    cache: "CacheType",
    redis_cache: "RedisCache | None" = None,
) -> None:
    """
    Initialize the shared context with rate limiter and cache.

    Called once at server startup.

    Args:
        rate_limiter: Global rate limiter instance
        cache: Shared cache instance (InMemoryCache or AsyncTieredCache)
        redis_cache: Optional Redis cache instance for L2 caching
    """
    global _rate_limiter, _cache, _redis_cache
    _rate_limiter = rate_limiter
    _cache = cache
    _redis_cache = redis_cache


def get_rate_limiter() -> "RateLimiter | None":
    """Get the global rate limiter instance."""
    return _rate_limiter


def get_cache() -> "CacheType | None":
    """Get the shared cache instance."""
    return _cache


def get_redis_cache() -> "RedisCache | None":
    """Get the Redis cache instance (if enabled)."""
    return _redis_cache
