"""
In-memory caching with TTL, stale fallback, and ETag support using cachetools.

Uses a single TTLCache with the stale TTL for storage, and tracks insertion
timestamps to determine freshness. This avoids storing data twice while still
supporting graceful degradation when rate limited.

ETag support enables conditional requests - when cached data has an ETag, clients
can send If-None-Match headers. A 304 response means data hasn't changed, avoiding
re-transfer and not counting against rate limits.
"""

import threading
import time
from datetime import UTC
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
        self._fresh_ttl = fresh_ttl
        self._stale_ttl = evict_ttl
        self._cache = TTLCache(maxsize=maxsize, ttl=self._stale_ttl)
        self._timestamps: dict[str, float] = {}
        self._etags: dict[str, str] = {}
        self._hits: dict[str, int] = {}
        self._last_accessed: dict[str, float] = {}
        self._total_hits = 0
        self._total_misses = 0
        self._etag_hits = 0
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
                self._etags.pop(key, None)
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

    def set(self, key: str, value: Any, etag: str | None = None) -> bool:
        """Set value in cache with optional ETag."""
        with self._lock:
            self._cache[key] = value
            self._timestamps[key] = time.time()
            if etag:
                self._etags[key] = etag
            return True

    def get_etag(self, key: str) -> str | None:
        """Get ETag for a cached key (if available)."""
        with self._lock:
            if key not in self._cache:
                return None
            return self._etags.get(key)

    def refresh(self, key: str, etag: str | None = None) -> bool:
        """
        Refresh TTL for a key (used on 304 Not Modified responses).

        This resets the timestamp to make the entry fresh again without
        changing the cached value. Optionally updates the ETag.
        """
        with self._lock:
            if key not in self._cache:
                return False
            self._timestamps[key] = time.time()
            self._etag_hits += 1
            if etag:
                self._etags[key] = etag
            return True

    def invalidate(self, key: str) -> bool:
        """Invalidate cache entry."""
        with self._lock:
            self._cache.pop(key, None)
            self._timestamps.pop(key, None)
            self._etags.pop(key, None)
            self._hits.pop(key, None)
            self._last_accessed.pop(key, None)
            return True

    def clear(self) -> bool:
        """Clear all cache entries."""
        with self._lock:
            self._cache.clear()
            self._timestamps.clear()
            self._etags.clear()
            self._hits.clear()
            self._last_accessed.clear()
            return True

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            now = time.time()
            fresh_count = sum(
                1
                for k in self._cache
                if k in self._timestamps
                and (now - self._timestamps[k]) < self._fresh_ttl
            )
            total = self._total_hits + self._total_misses
            return {
                "size": len(self._cache),
                "fresh_count": fresh_count,
                "stale_count": len(self._cache) - fresh_count,
                "maxsize": self._cache.maxsize,
                "hit_rate": round(self._total_hits / total, 2) if total > 0 else 0,
                "etag_hits": self._etag_hits,
            }

    def get_detailed_stats(self, top: int = 20) -> dict[str, Any]:
        """Get detailed cache statistics with per-key info."""
        from datetime import datetime

        def to_iso(ts: float) -> str:
            return datetime.fromtimestamp(ts, tz=UTC).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )

        with self._lock:
            now = time.time()
            keys = []
            for key in self._cache:
                created = self._timestamps.get(key, now)
                keys.append(
                    {
                        "key": key,
                        "hits": self._hits.get(key, 0),
                        "created": to_iso(created),
                        "last_accessed": to_iso(self._last_accessed.get(key, created)),
                        "is_fresh": (now - created) < self._fresh_ttl,
                        "has_etag": key in self._etags,
                    }
                )
            keys.sort(key=lambda x: x["hits"], reverse=True)
            total = self._total_hits + self._total_misses
            return {
                "summary": {
                    "size": len(self._cache),
                    "total_hits": self._total_hits,
                    "total_misses": self._total_misses,
                    "hit_rate": round(self._total_hits / total, 2) if total > 0 else 0,
                    "etag_hits": self._etag_hits,
                    "timezone": "UTC",
                },
                "keys": keys[:top],
            }


Cache = InMemoryCache
