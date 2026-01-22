"""
Caching with cachetools + stale cache for graceful degradation.

Provides a thin wrapper around cachetools.TTLCache that adds stale cache support
for serving expired entries during rate limiting. Both the primary cache and the
stale cache use TTLCache with automatic TTL expiration and LRU eviction. The stale
cache has a longer TTL (24x) to preserve entries for graceful degradation when
fresh data is unavailable due to rate limits.
"""

import threading
from typing import Any

from cachetools import TTLCache


class InMemoryCache:
    """Thread-safe cache with stale fallback using cachetools.TTLCache."""

    def __init__(self, ttl: int = 3600, maxsize: int = 1000):
        self._cache = TTLCache(maxsize=maxsize, ttl=ttl)
        # Stale cache: longer TTL (24x) and larger size (2x) for graceful degradation
        self._stale_cache = TTLCache(maxsize=maxsize * 2, ttl=ttl * 24)
        self._lock = threading.RLock()

    def get(self, key: str, allow_stale: bool = False) -> Any:
        """Get value from cache, optionally including stale entries."""
        with self._lock:
            if key in self._cache:
                return self._cache[key]
            if allow_stale and key in self._stale_cache:
                return self._stale_cache[key]
            return None

    def set(self, key: str, value: Any) -> bool:
        """Set value in cache."""
        with self._lock:
            try:
                self._cache[key] = value
                self._stale_cache[key] = value
                return True
            except Exception:
                return False

    def invalidate(self, key: str) -> bool:
        """Invalidate cache entry."""
        with self._lock:
            try:
                self._cache.pop(key, None)
                self._stale_cache.pop(key, None)
                return True
            except Exception:
                return False

    def clear(self) -> bool:
        """Clear all cache entries."""
        with self._lock:
            try:
                self._cache.clear()
                self._stale_cache.clear()
                return True
            except Exception:
                return False

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            return {
                "size": len(self._cache),
                "maxsize": self._cache.maxsize,
                "ttl": self._cache.ttl,
                "stale_size": len(self._stale_cache),
                "stale_maxsize": self._stale_cache.maxsize,
            }


Cache = InMemoryCache
