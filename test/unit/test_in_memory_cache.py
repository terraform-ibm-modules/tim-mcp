"""Unit tests for InMemoryCache."""

import threading
import time

from tim_mcp.utils.cache import InMemoryCache


class TestInMemoryCache:
    """Test suite for InMemoryCache class."""

    def test_cache_get_set(self):
        """Test basic get/set operations."""
        cache = InMemoryCache(fresh_ttl=10, maxsize=10)

        # Test set and get
        assert cache.set("key1", "value1") is True
        assert cache.get("key1") == "value1"

        # Test get missing key
        assert cache.get("missing_key") is None

    def test_cache_ttl_expiration(self):
        """Test that cache entries expire after TTL (become stale)."""
        cache = InMemoryCache(fresh_ttl=1, maxsize=10)

        # Set a value
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

        # Wait for fresh TTL to expire
        time.sleep(1.1)

        # Fresh get should return None (entry is stale)
        assert cache.get("key1") is None

    def test_cache_stale_fallback(self):
        """Test that allow_stale returns expired entries."""
        cache = InMemoryCache(fresh_ttl=1, evict_ttl=10, maxsize=10)

        # Set a value
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

        # Wait for fresh TTL to expire
        time.sleep(1.1)

        # Normal get should return None
        assert cache.get("key1") is None

        # Stale get should return the value
        assert cache.get("key1", allow_stale=True) == "value1"

    def test_cache_lru_eviction(self):
        """Test that LRU eviction works when maxsize exceeded."""
        cache = InMemoryCache(fresh_ttl=100, maxsize=2)

        # Fill cache to capacity
        cache.set("key1", "value1")
        cache.set("key2", "value2")

        # Both should be present
        assert cache.get("key1") == "value1"
        assert cache.get("key2") == "value2"

        # Add third item (should evict oldest)
        cache.set("key3", "value3")

        # key2 and key3 should still be present
        assert cache.get("key2") == "value2"
        assert cache.get("key3") == "value3"

    def test_cache_invalidate(self):
        """Test cache invalidation."""
        cache = InMemoryCache(fresh_ttl=10, maxsize=10)

        # Set a value
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

        # Invalidate it
        assert cache.invalidate("key1") is True

        # Should be gone
        assert cache.get("key1") is None
        assert cache.get("key1", allow_stale=True) is None

        # Invalidating non-existent key should succeed
        assert cache.invalidate("missing_key") is True

    def test_cache_clear(self):
        """Test clearing all cache entries."""
        cache = InMemoryCache(fresh_ttl=10, maxsize=10)

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

    def test_cache_thread_safety(self):
        """Test that cache is thread-safe."""
        cache = InMemoryCache(fresh_ttl=10, maxsize=100)
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

    def test_cache_complex_values(self):
        """Test caching complex data types."""
        cache = InMemoryCache(fresh_ttl=10, maxsize=10)

        # Test dict
        cache.set("dict_key", {"name": "test", "value": 123})
        result = cache.get("dict_key")
        assert result == {"name": "test", "value": 123}

        # Test list
        cache.set("list_key", [1, 2, 3, 4, 5])
        assert cache.get("list_key") == [1, 2, 3, 4, 5]

        # Test nested structures
        nested = {"data": [{"id": 1, "items": [1, 2, 3]}, {"id": 2, "items": [4, 5, 6]}]}
        cache.set("nested_key", nested)
        assert cache.get("nested_key") == nested

    def test_cache_update_existing_key(self):
        """Test updating an existing cache entry."""
        cache = InMemoryCache(fresh_ttl=1, evict_ttl=10, maxsize=10)

        # Set initial value
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

        # Update value
        cache.set("key1", "value2")
        assert cache.get("key1") == "value2"

        # Should also update the value in stale cache
        time.sleep(1.1)
        assert cache.get("key1", allow_stale=True) == "value2"

    def test_cache_equal_ttls_allowed(self):
        """Test that evict_ttl == fresh_ttl is allowed."""
        # This should not raise an error
        cache = InMemoryCache(fresh_ttl=3600, evict_ttl=3600)
        assert cache is not None

        # Verify cache works normally
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_cache_evict_ttl_less_than_fresh_ttl_raises_error(self):
        """Test that evict_ttl < fresh_ttl raises ValueError."""
        import pytest

        with pytest.raises(ValueError) as exc_info:
            InMemoryCache(fresh_ttl=3600, evict_ttl=1800)

        assert "must be greater than or equal to" in str(exc_info.value)
        assert "3600" in str(exc_info.value)  # fresh_ttl
        assert "1800" in str(exc_info.value)  # evict_ttl

    def test_cache_disabled_with_zero_ttls(self):
        """Test that both TTLs can be set to 0 (disabled cache scenario from generate_module_index.py)."""
        # This is the scenario from generate_module_index.py: Cache(fresh_ttl=0, evict_ttl=0)
        cache = InMemoryCache(fresh_ttl=0, evict_ttl=0)
        assert cache is not None

        # Cache should work but entries expire immediately
        cache.set("key1", "value1")
        # With TTL=0, entry may or may not be retrievable depending on timing
        # Just verify no errors occur during initialization and basic operations
