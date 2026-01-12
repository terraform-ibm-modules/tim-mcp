"""
Cache utilities for Tim MCP.

This module provides in-memory caching functionality with TTL and LRU eviction
to improve performance by storing frequently accessed data.
"""

import threading
from typing import Any

from cachetools import TTLCache

from ..logging import get_logger

logger = get_logger(__name__)


class InMemoryCache:
    """
    Thread-safe in-memory cache with TTL and LRU eviction.

    Uses cachetools.TTLCache for automatic expiration and eviction.
    Maintains a separate stale cache for graceful degradation during rate limiting.
    """

    def __init__(self, ttl: int = 3600, maxsize: int = 1000):
        """
        Initialize the in-memory cache.

        Args:
            ttl: Time-to-live in seconds (default: 3600 = 1 hour)
            maxsize: Maximum number of cache entries (default: 1000)
                    When exceeded, least recently used entries are evicted
        """
        # TTLCache combines LRU + TTL: evicts oldest items when full,
        # automatically expires items after TTL
        self._cache = TTLCache(maxsize=maxsize, ttl=ttl)

        # Separate dict to store expired entries for stale fallback
        # This allows serving old data when rate limited
        self._stale_cache: dict[str, Any] = {}

        # Reentrant lock for thread safety (allows nested calls)
        self._lock = threading.RLock()

        self.ttl = ttl
        self.maxsize = maxsize

        logger.debug(
            "In-memory cache initialized",
            ttl=ttl,
            maxsize=maxsize
        )

    def get(self, key: str, allow_stale: bool = False) -> Any:
        """
        Get a value from the cache.

        Args:
            key: Cache key
            allow_stale: If True, return expired entries from stale cache
                        (used for rate limit fallback)

        Returns:
            Cached value, or None if not found
        """
        with self._lock:
            # Check active cache first
            if key in self._cache:
                logger.debug("Cache hit", cache_key=key)
                return self._cache[key]

            # If allow_stale, check stale cache
            if allow_stale and key in self._stale_cache:
                logger.info(
                    "Serving stale cache entry",
                    cache_key=key,
                    reason="allow_stale=True"
                )
                return self._stale_cache[key]

            logger.debug("Cache miss", cache_key=key)
            return None

    def set(self, key: str, value: Any) -> bool:
        """
        Set a value in the cache.

        Args:
            key: Cache key
            value: Value to cache

        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            try:
                # Store in both caches:
                # - TTLCache for normal access with expiration
                # - stale_cache for fallback when rate limited
                self._cache[key] = value
                self._stale_cache[key] = value

                logger.debug("Cached value", cache_key=key)
                return True
            except Exception as e:
                logger.warning(
                    "Error caching value",
                    cache_key=key,
                    error=str(e)
                )
                return False

    def invalidate(self, key: str) -> bool:
        """
        Invalidate a cache entry.

        Args:
            key: Cache key

        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            try:
                # Remove from both caches
                if key in self._cache:
                    del self._cache[key]
                    logger.debug("Invalidated cache entry", cache_key=key)

                if key in self._stale_cache:
                    del self._stale_cache[key]

                return True
            except Exception as e:
                logger.warning(
                    "Error invalidating cache",
                    cache_key=key,
                    error=str(e)
                )
                return False

    def clear(self) -> bool:
        """
        Clear all cache entries.

        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            try:
                self._cache.clear()
                self._stale_cache.clear()
                logger.debug("Cleared all cache entries")
                return True
            except Exception as e:
                logger.warning("Error clearing cache", error=str(e))
                return False

    def get_stats(self) -> dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache statistics:
            - size: Current number of active entries
            - maxsize: Maximum cache size
            - ttl: Time-to-live in seconds
            - stale_entries: Number of stale entries available for fallback
        """
        with self._lock:
            return {
                "size": len(self._cache),
                "maxsize": self.maxsize,
                "ttl": self.ttl,
                "stale_entries": len(self._stale_cache) - len(self._cache)
            }


# Backward compatibility alias
Cache = InMemoryCache
