"""
In-memory caching with TTL and stale fallback using cachetools.

Uses a single TTLCache with the stale TTL for storage, and tracks insertion
timestamps to determine freshness. This avoids storing data twice while still
supporting graceful degradation when rate limited.
"""

import threading
import time
from typing import Any

from cachetools import TTLCache


class InMemoryCache:
    """Thread-safe cache with stale fallback using a single TTLCache."""

    def __init__(self, ttl: int = 3600, maxsize: int = 1000, stale_ttl_multiplier: int = 24):
        """
        Initialize the cache.

        Args:
            ttl: Fresh cache TTL in seconds (entries older than this are "stale")
            maxsize: Maximum cache entries
            stale_ttl_multiplier: Total TTL = ttl * multiplier (entries expire completely after this)
        """
        self._fresh_ttl = ttl
        self._stale_ttl = ttl * stale_ttl_multiplier
        self._cache = TTLCache(maxsize=maxsize, ttl=self._stale_ttl)
        self._timestamps: dict[str, float] = {}
        self._lock = threading.RLock()

    def _is_fresh(self, key: str) -> bool:
        """Check if an entry is still fresh (within primary TTL)."""
        if key not in self._timestamps:
            return False
        return (time.time() - self._timestamps[key]) < self._fresh_ttl

    def get(self, key: str, allow_stale: bool = False) -> Any:
        """Get value from cache, optionally including stale entries."""
        with self._lock:
            if key not in self._cache:
                return None
            if allow_stale or self._is_fresh(key):
                return self._cache[key]
            return None

    def set(self, key: str, value: Any) -> bool:
        """Set value in cache."""
        with self._lock:
            try:
                self._cache[key] = value
                self._timestamps[key] = time.time()
                return True
            except Exception:
                return False

    def invalidate(self, key: str) -> bool:
        """Invalidate cache entry."""
        with self._lock:
            try:
                self._cache.pop(key, None)
                self._timestamps.pop(key, None)
                return True
            except Exception:
                return False

    def clear(self) -> bool:
        """Clear all cache entries."""
        with self._lock:
            try:
                self._cache.clear()
                self._timestamps.clear()
                return True
            except Exception:
                return False

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            now = time.time()
            fresh_count = sum(
                1 for k in self._cache if k in self._timestamps and (now - self._timestamps[k]) < self._fresh_ttl
            )
            return {
                "size": len(self._cache),
                "fresh_count": fresh_count,
                "stale_count": len(self._cache) - fresh_count,
                "maxsize": self._cache.maxsize,
                "fresh_ttl": self._fresh_ttl,
                "stale_ttl": self._stale_ttl,
            }


Cache = InMemoryCache
