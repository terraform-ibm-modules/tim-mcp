"""In-memory caching with fresh/stale TTL and ETag support using cachetools."""

from threading import RLock
from typing import Any

from cachetools import TTLCache


class InMemoryCache:
    """Thread-safe cache with stale fallback and ETag support."""

    def __init__(
        self, fresh_ttl: int = 3600, evict_ttl: int = 86400, maxsize: int = 1000
    ):
        """
        Initialize the cache.

        Args:
            fresh_ttl: TTL for fresh entries in seconds (default: 1 hour)
            evict_ttl: TTL before eviction in seconds (default: 24 hours)
            maxsize: Maximum cache entries per cache
        """
        self._fresh = TTLCache(maxsize=maxsize, ttl=fresh_ttl)
        self._stale = TTLCache(maxsize=maxsize, ttl=evict_ttl)
        self._etags: dict[str, str] = {}
        self._lock = RLock()

    def get(self, key: str, allow_stale: bool = False) -> Any:
        """Get value from cache, optionally including stale entries."""
        with self._lock:
            if key in self._fresh:
                return self._fresh[key]
            if allow_stale and key in self._stale:
                return self._stale[key]
            return None

    def set(self, key: str, value: Any, etag: str | None = None) -> bool:
        """Set value in cache with optional ETag."""
        with self._lock:
            self._fresh[key] = value
            self._stale[key] = value
            if etag:
                self._etags[key] = etag
            return True

    def get_etag(self, key: str) -> str | None:
        """Get stored ETag for a cache key."""
        with self._lock:
            return self._etags.get(key)

    def refresh(self, key: str, etag: str | None = None) -> bool:
        """
        Refresh cache entry TTL (used on 304 Not Modified responses).

        Re-inserts the value to reset TTL without changing the data.
        """
        with self._lock:
            if key not in self._stale:
                return False
            value = self._stale[key]
            self._fresh[key] = value
            self._stale[key] = value
            if etag:
                self._etags[key] = etag
            return True

    def invalidate(self, key: str) -> bool:
        """Invalidate cache entry."""
        with self._lock:
            self._fresh.pop(key, None)
            self._stale.pop(key, None)
            self._etags.pop(key, None)
            return True

    def clear(self) -> bool:
        """Clear all cache entries."""
        with self._lock:
            self._fresh.clear()
            self._stale.clear()
            self._etags.clear()
            return True


Cache = InMemoryCache
