"""Redis cache backend using aiocache with fresh/stale TTL support."""

import time
from typing import Any
from urllib.parse import urlparse

from aiocache import Cache
from aiocache.serializers import JsonSerializer

from ..logging import get_logger

logger = get_logger(__name__)


class RedisCache:
    """Async Redis cache with fresh/stale TTL support, powered by aiocache."""

    def __init__(
        self,
        url: str = "redis://localhost:6379",
        ttl: int = 3600,
        stale_ttl_multiplier: int = 48,
        key_prefix: str = "tim:cache:",
    ):
        self._fresh_ttl = ttl
        self._stale_ttl = ttl * stale_ttl_multiplier

        # Parse URL for aiocache (requires host/port separately)
        parsed = urlparse(url)
        self._cache = Cache(
            Cache.REDIS,
            endpoint=parsed.hostname or "localhost",
            port=parsed.port or 6379,
            namespace=key_prefix,
            serializer=JsonSerializer(),
            ttl=self._stale_ttl,
        )

    async def connect(self) -> bool:
        """Test Redis connection."""
        try:
            await self._cache.exists("__ping__")
            logger.info("Connected to Redis via aiocache")
            return True
        except Exception as e:
            logger.warning("Failed to connect to Redis", error=str(e))
            return False

    async def close(self) -> None:
        """Close Redis connection."""
        await self._cache.close()

    async def get(self, key: str, allow_stale: bool = False) -> Any:
        """Get value from Redis, optionally allowing stale entries."""
        try:
            entry = await self._cache.get(key)
            if entry is None:
                return None

            age = time.time() - entry.get("created", 0)
            if allow_stale or age < self._fresh_ttl:
                return entry.get("value")
            return None
        except Exception as e:
            logger.warning("Redis get failed", key=key, error=str(e))
            return None

    async def set(self, key: str, value: Any) -> bool:
        """Set value in Redis with TTL."""
        try:
            await self._cache.set(key, {"value": value, "created": time.time()})
            return True
        except Exception as e:
            logger.warning("Redis set failed", key=key, error=str(e))
            return False
