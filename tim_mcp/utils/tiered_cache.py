"""Tiered cache: L1 (memory) + L2 (Redis)."""

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from .redis_cache import RedisCache


class CacheProtocol(Protocol):
    """Protocol for cache implementations."""

    def get(self, key: str, allow_stale: bool = False) -> Any: ...
    def set(self, key: str, value: Any) -> bool: ...


class AsyncTieredCache:
    """Async tiered cache for use in async contexts."""

    def __init__(self, l1: CacheProtocol, l2: "RedisCache | None" = None):
        """
        Initialize async tiered cache.

        Args:
            l1: L1 (memory) cache instance
            l2: Optional L2 (Redis) cache instance
        """
        self._l1 = l1
        self._l2 = l2

    async def get(self, key: str, allow_stale: bool = False) -> Any:
        """Get from L1 first, then L2."""
        # Try L1
        value = self._l1.get(key, allow_stale=allow_stale)
        if value is not None:
            return value

        # Try L2
        if self._l2:
            value = await self._l2.get(key, allow_stale=allow_stale)
            if value is not None:
                # Populate L1
                self._l1.set(key, value)
                return value

        return None

    async def set(self, key: str, value: Any) -> bool:
        """Write to both L1 and L2."""
        self._l1.set(key, value)
        if self._l2:
            await self._l2.set(key, value)
        return True
