"""Tiered cache: L1 (memory) + L2 (Redis)."""

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from .redis_cache import RedisCache


class CacheProtocol(Protocol):
    """Protocol for cache implementations."""

    def get(self, key: str, allow_stale: bool = False) -> Any: ...
    def set(self, key: str, value: Any) -> bool: ...
    def get_stats(self) -> dict[str, Any]: ...


class TieredCache:
    """L1 (memory) + L2 (Redis) cache with sync interface."""

    def __init__(self, l1: CacheProtocol, l2: CacheProtocol | None = None):
        """
        Initialize tiered cache.

        Args:
            l1: L1 (memory) cache instance
            l2: Optional L2 (Redis) cache instance
        """
        self._l1 = l1
        self._l2 = l2

    def get(self, key: str, allow_stale: bool = False) -> Any:
        """Get from L1 only (sync interface)."""
        return self._l1.get(key, allow_stale=allow_stale)

    def set(self, key: str, value: Any) -> bool:
        """Write to L1 only (sync interface)."""
        return self._l1.set(key, value)

    def get_stats(self) -> dict[str, Any]:
        """Get combined stats."""
        return {
            "l1": self._l1.get_stats(),
            "l2_enabled": self._l2 is not None,
        }


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

    def get_sync(self, key: str, allow_stale: bool = False) -> Any:
        """Sync get from L1 only (for decorator compatibility)."""
        return self._l1.get(key, allow_stale=allow_stale)

    def set_sync(self, key: str, value: Any) -> bool:
        """Sync set to L1 only (L2 populated on next async operation)."""
        return self._l1.set(key, value)

    def get_stats(self) -> dict[str, Any]:
        """Get L1 stats (L2 stats are async)."""
        return self._l1.get_stats()

    async def get_combined_stats(self) -> dict[str, Any]:
        """Get combined L1 and L2 stats."""
        stats = {
            "l1": self._l1.get_stats(),
            "l2_enabled": self._l2 is not None,
        }
        if self._l2:
            stats["l2"] = await self._l2.get_stats()
        return stats
