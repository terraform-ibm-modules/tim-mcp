"""Unit tests for InMemoryCache."""

import pytest
import time
import threading
from tim_mcp.utils.cache import InMemoryCache


class TestInMemoryCache:
    """Test suite for InMemoryCache class."""

    def test_cache_get_set(self):
        """Test basic get/set operations."""
        cache = InMemoryCache(ttl=10, maxsize=10)

        # Test set and get
        assert cache.set("key1", "value1") is True
        assert cache.get("key1") == "value1"

        # Test get missing key
        assert cache.get("missing_key") is None

    def test_cache_ttl_expiration(self):
        """Test that cache entries expire after TTL."""
        cache = InMemoryCache(ttl=1, maxsize=10)

        # Set a value
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

        # Wait for TTL to expire
        time.sleep(1.1)

        # Value should be expired
        assert cache.get("key1") is None

    def test_cache_stale_fallback(self):
        """Test that allow_stale returns expired entries."""
        cache = InMemoryCache(ttl=1, maxsize=10)

        # Set a value
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

        # Wait for TTL to expire
        time.sleep(1.1)

        # Normal get should return None
        assert cache.get("key1") is None

        # Stale get should return the value
        assert cache.get("key1", allow_stale=True) == "value1"

    def test_cache_lru_eviction(self):
        """Test that LRU eviction works when maxsize exceeded."""
        cache = InMemoryCache(ttl=100, maxsize=2)

        # Fill cache to capacity
        cache.set("key1", "value1")
        cache.set("key2", "value2")

        # Both should be present
        assert cache.get("key1") == "value1"
        assert cache.get("key2") == "value2"

        # Add third item (should evict key1 as it's least recently used)
        cache.set("key3", "value3")

        # key1 should be evicted from active cache
        assert cache.get("key1") is None

        # key2 and key3 should still be present
        assert cache.get("key2") == "value2"
        assert cache.get("key3") == "value3"

        # But key1 should still be in stale cache
        assert cache.get("key1", allow_stale=True) == "value1"

    def test_cache_invalidate(self):
        """Test cache invalidation."""
        cache = InMemoryCache(ttl=10, maxsize=10)

        # Set a value
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

        # Invalidate it
        assert cache.invalidate("key1") is True

        # Should be gone from both caches
        assert cache.get("key1") is None
        assert cache.get("key1", allow_stale=True) is None

        # Invalidating non-existent key should succeed
        assert cache.invalidate("missing_key") is True

    def test_cache_clear(self):
        """Test clearing all cache entries."""
        cache = InMemoryCache(ttl=10, maxsize=10)

        # Add multiple entries
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")

        # Verify they exist
        assert cache.get("key1") == "value1"
        assert cache.get("key2") == "value2"

        # Clear cache
        assert cache.clear() is True

        # All should be gone
        assert cache.get("key1") is None
        assert cache.get("key2") is None
        assert cache.get("key3") is None

        # Should also clear stale cache
        assert cache.get("key1", allow_stale=True) is None

    def test_cache_stats(self):
        """Test cache statistics."""
        cache = InMemoryCache(ttl=1, maxsize=5)

        # Empty cache stats
        stats = cache.get_stats()
        assert stats["size"] == 0
        assert stats["maxsize"] == 5
        assert stats["ttl"] == 1
        assert stats["stale_size"] == 0

        # Add entries (stored in both primary and stale cache for graceful degradation)
        cache.set("key1", "value1")
        cache.set("key2", "value2")

        stats = cache.get_stats()
        assert stats["size"] == 2
        assert stats["stale_size"] == 2  # Also in stale cache for fallback

        # Wait for primary cache expiration (stale cache has longer TTL)
        time.sleep(1.1)

        # Trigger expiration check by accessing cache
        cache.get("key1")

        stats = cache.get_stats()
        assert stats["size"] == 0  # Expired from active cache
        assert stats["stale_size"] == 2  # Still in stale cache (24x TTL)

    def test_cache_thread_safety(self):
        """Test that cache is thread-safe."""
        cache = InMemoryCache(ttl=10, maxsize=100)
        errors = []

        def write_values(start, end):
            """Write values to cache."""
            try:
                for i in range(start, end):
                    cache.set(f"key{i}", f"value{i}")
            except Exception as e:
                errors.append(e)

        def read_values(start, end):
            """Read values from cache."""
            try:
                for i in range(start, end):
                    cache.get(f"key{i}")
            except Exception as e:
                errors.append(e)

        # Create multiple threads
        threads = []
        threads.append(threading.Thread(target=write_values, args=(0, 50)))
        threads.append(threading.Thread(target=write_values, args=(50, 100)))
        threads.append(threading.Thread(target=read_values, args=(0, 50)))
        threads.append(threading.Thread(target=read_values, args=(50, 100)))

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # No errors should have occurred
        assert len(errors) == 0

        # Cache should have entries
        stats = cache.get_stats()
        assert stats["size"] > 0

    def test_cache_complex_values(self):
        """Test caching complex data types."""
        cache = InMemoryCache(ttl=10, maxsize=10)

        # Test dict
        cache.set("dict_key", {"name": "test", "value": 123})
        result = cache.get("dict_key")
        assert result == {"name": "test", "value": 123}

        # Test list
        cache.set("list_key", [1, 2, 3, 4, 5])
        assert cache.get("list_key") == [1, 2, 3, 4, 5]

        # Test nested structures
        nested = {
            "data": [
                {"id": 1, "items": [1, 2, 3]},
                {"id": 2, "items": [4, 5, 6]}
            ]
        }
        cache.set("nested_key", nested)
        assert cache.get("nested_key") == nested

    def test_cache_update_existing_key(self):
        """Test updating an existing cache entry."""
        cache = InMemoryCache(ttl=10, maxsize=10)

        # Set initial value
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

        # Update value
        cache.set("key1", "value2")
        assert cache.get("key1") == "value2"

        # Should also update stale cache
        time.sleep(11)  # Wait for TTL to expire
        assert cache.get("key1", allow_stale=True) == "value2"
