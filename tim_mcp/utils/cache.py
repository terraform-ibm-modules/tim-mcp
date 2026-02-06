"""In-memory caching with fresh/stale TTL using cachetools."""

from threading import RLock
from typing import Any

from cachetools import TTLCache


class InMemoryCache:
    """Thread-safe cache with stale fallback using two TTLCache instances."""

    def __init__(
        self, fresh_ttl: int = 3600, evict_ttl: int = 86400, maxsize: int = 1000
    ):
        """
        Initialize the cache.

        Args:
            fresh_ttl: TTL for fresh entries in seconds (default: 1 hour)
            evict_ttl: TTL before eviction in seconds (default: 24 hours)
            maxsize: Maximum cache entries per cache
        
        Raises:
            ValueError: If evict_ttl is not greater than or equal to fresh_ttl
        """
        if evict_ttl < fresh_ttl:
            raise ValueError(
                f"evict_ttl ({evict_ttl}) must be greater than or equal to fresh_ttl ({fresh_ttl})"
            )
        self._fresh = TTLCache(maxsize=maxsize, ttl=fresh_ttl)
        self._stale = TTLCache(maxsize=maxsize, ttl=evict_ttl)
        self._lock = RLock()

    def get(self, key: str, allow_stale: bool = False) -> Any:
        """Get value from cache, optionally including stale entries."""
        with self._lock:
            if key in self._fresh:
                return self._fresh[key]
            if allow_stale and key in self._stale:
                return self._stale[key]
            return None

    def set(self, key: str, value: Any) -> bool:
        """Set value in cache."""
        with self._lock:
            self._fresh[key] = value
            self._stale[key] = value
            return True

    def invalidate(self, key: str) -> bool:
        """Invalidate cache entry."""
        with self._lock:
            self._fresh.pop(key, None)
            self._stale.pop(key, None)
            return True

    def clear(self) -> bool:
        """Clear all cache entries."""
        with self._lock:
            self._fresh.clear()
            self._stale.clear()
            return True


Cache = InMemoryCache
