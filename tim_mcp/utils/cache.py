"""Caching with cachetools + stale cache for graceful degradation."""

import threading
from typing import Any

from cachetools import TTLCache


class InMemoryCache:
    """Thread-safe cache with stale fallback using cachetools.TTLCache."""

    def __init__(self, ttl: int = 3600, maxsize: int = 1000):
        self._cache = TTLCache(maxsize=maxsize, ttl=ttl)
        self._stale_cache: dict[str, Any] = {}
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
                "stale_entries": len(self._stale_cache) - len(self._cache)
            }


Cache = InMemoryCache
