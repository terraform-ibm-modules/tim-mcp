"""Redis cache backend with same interface as InMemoryCache."""

import json
import time
from typing import Any

import redis.asyncio as redis

from ..logging import get_logger


class RedisCache:
    """Async Redis cache with fresh/stale TTL support."""

    def __init__(
        self,
        url: str = "redis://localhost:6379",
        ttl: int = 3600,
        stale_ttl_multiplier: int = 48,
        key_prefix: str = "tim:cache:",
    ):
        """
        Initialize the Redis cache.

        Args:
            url: Redis connection URL
            ttl: Fresh cache TTL in seconds (entries older than this are "stale")
            stale_ttl_multiplier: Multiplier for stale TTL. Total TTL = ttl * multiplier.
                Default 48 means stale entries persist for 48 hours with daily sync.
            key_prefix: Prefix for all Redis keys
        """
        self._fresh_ttl = ttl
        self._stale_ttl = ttl * stale_ttl_multiplier
        self._prefix = key_prefix
        self._client: redis.Redis | None = None
        self._url = url
        self._logger = get_logger(__name__)
        self._total_hits = 0
        self._total_misses = 0

    async def connect(self) -> bool:
        """Initialize Redis connection. Returns True if successful."""
        try:
            self._client = redis.from_url(
                self._url,
                encoding="utf-8",
                decode_responses=True,
            )
            await self._client.ping()
            self._logger.info("Connected to Redis", url=self._url)
            return True
        except Exception as e:
            self._logger.warning("Failed to connect to Redis", error=str(e))
            self._client = None
            return False

    async def close(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _key(self, key: str) -> str:
        """Generate prefixed Redis key."""
        return f"{self._prefix}{key}"

    def _is_fresh(self, created: float) -> bool:
        """Check if an entry is still fresh (within primary TTL)."""
        return (time.time() - created) < self._fresh_ttl

    async def get(self, key: str, allow_stale: bool = False) -> Any:
        """Get value from Redis."""
        if not self._client:
            return None
        try:
            data = await self._client.get(self._key(key))
            if not data:
                self._total_misses += 1
                return None

            entry = json.loads(data)
            created = entry.get("created", 0)

            if allow_stale or self._is_fresh(created):
                self._total_hits += 1
                return entry.get("value")

            self._total_misses += 1
            return None
        except Exception as e:
            self._logger.warning("Redis get failed", key=key, error=str(e))
            return None

    async def set(self, key: str, value: Any) -> bool:
        """Set value in Redis with TTL."""
        if not self._client:
            return False
        try:
            entry = {"value": value, "created": time.time()}
            await self._client.setex(
                self._key(key),
                self._stale_ttl,
                json.dumps(entry, default=str),
            )
            return True
        except Exception as e:
            self._logger.warning("Redis set failed", key=key, error=str(e))
            return False

    async def invalidate(self, key: str) -> bool:
        """Delete key from Redis."""
        if not self._client:
            return False
        try:
            await self._client.delete(self._key(key))
            return True
        except Exception:
            return False

    async def clear(self) -> bool:
        """Clear all keys with our prefix (use with caution)."""
        if not self._client:
            return False
        try:
            cursor = 0
            while True:
                cursor, keys = await self._client.scan(
                    cursor, match=f"{self._prefix}*", count=100
                )
                if keys:
                    await self._client.delete(*keys)
                if cursor == 0:
                    break
            return True
        except Exception:
            return False

    async def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total = self._total_hits + self._total_misses
        stats = {
            "backend": "redis",
            "connected": self._client is not None,
            "hit_rate": round(self._total_hits / total, 2) if total > 0 else 0,
            "total_hits": self._total_hits,
            "total_misses": self._total_misses,
        }

        if self._client:
            try:
                info = await self._client.info("keyspace")
                db_info = info.get("db0", {})
                stats["keys"] = db_info.get("keys", 0)
            except Exception:
                pass

        return stats
