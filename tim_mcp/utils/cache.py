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
        self._hits: dict[str, int] = {}
        self._last_accessed: dict[str, float] = {}
        self._total_hits = 0
        self._total_misses = 0
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
                self._timestamps.pop(key, None)
                self._hits.pop(key, None)
                self._last_accessed.pop(key, None)
                self._total_misses += 1
                return None
            if allow_stale or self._is_fresh(key):
                self._hits[key] = self._hits.get(key, 0) + 1
                self._last_accessed[key] = time.time()
                self._total_hits += 1
                return self._cache[key]
            self._total_misses += 1
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
                self._hits.pop(key, None)
                self._last_accessed.pop(key, None)
                return True
            except Exception:
                return False

    def clear(self) -> bool:
        """Clear all cache entries."""
        with self._lock:
            try:
                self._cache.clear()
                self._timestamps.clear()
                self._hits.clear()
                self._last_accessed.clear()
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
            total = self._total_hits + self._total_misses
            return {
                "size": len(self._cache),
                "fresh_count": fresh_count,
                "stale_count": len(self._cache) - fresh_count,
                "maxsize": self._cache.maxsize,
                "hit_rate": round(self._total_hits / total, 2) if total > 0 else 0,
            }

    def get_detailed_stats(self, top: int = 20) -> dict[str, Any]:
        """Get detailed cache statistics with per-key info."""
        with self._lock:
            now = time.time()
            keys = []
            for key in self._cache:
                created = self._timestamps.get(key, now)
                keys.append({
                    "key": key,
                    "hits": self._hits.get(key, 0),
                    "created": int(created),
                    "last_accessed": int(self._last_accessed.get(key, created)),
                    "is_fresh": (now - created) < self._fresh_ttl,
                })
            keys.sort(key=lambda x: x["hits"], reverse=True)
            total = self._total_hits + self._total_misses
            return {
                "summary": {
                    "size": len(self._cache),
                    "total_hits": self._total_hits,
                    "total_misses": self._total_misses,
                    "hit_rate": round(self._total_hits / total, 2) if total > 0 else 0,
                },
                "keys": keys[:top],
            }


Cache = InMemoryCache
