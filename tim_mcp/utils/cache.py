"""
Cache utilities for Tim MCP.

This module provides caching functionality to improve performance
by storing frequently accessed data.
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class Cache:
    """Simple file-based cache implementation."""

    def __init__(self, cache_dir: str | None = None, ttl: int = 3600):
        """
        Initialize the cache.

        Args:
            cache_dir: Cache directory, or None to use default
            ttl: Time-to-live in seconds (default: 1 hour)
        """
        if cache_dir is None:
            home_dir = os.path.expanduser("~")
            cache_dir = os.path.join(home_dir, ".tim-mcp", "cache")

        self.cache_dir = Path(cache_dir)
        self.ttl = ttl

        # Create cache directory if it doesn't exist
        os.makedirs(self.cache_dir, exist_ok=True)
        logger.debug(f"Cache initialized at {self.cache_dir}")

    def _get_cache_path(self, key: str) -> Path:
        """
        Get the file path for a cache key.

        Args:
            key: Cache key

        Returns:
            Path to cache file
        """
        # Convert key to a valid filename
        safe_key = "".join(c if c.isalnum() else "_" for c in key)
        return self.cache_dir / f"{safe_key}.json"

    def get(self, key: str) -> Any:
        """
        Get a value from the cache.

        Args:
            key: Cache key

        Returns:
            Cached value, or None if not found or expired
        """
        cache_path = self._get_cache_path(key)

        if not cache_path.exists():
            logger.debug(f"Cache miss for key: {key}")
            return None

        try:
            with open(cache_path) as f:
                cache_data = json.load(f)

            # Check if cache has expired
            if time.time() - cache_data["timestamp"] > self.ttl:
                logger.debug(f"Cache expired for key: {key}")
                os.remove(cache_path)
                return None

            logger.debug(f"Cache hit for key: {key}")
            return cache_data["value"]
        except (OSError, json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Error reading cache for key {key}: {e}")
            return None

    def set(self, key: str, value: Any) -> bool:
        """
        Set a value in the cache.

        Args:
            key: Cache key
            value: Value to cache

        Returns:
            True if successful, False otherwise
        """
        cache_path = self._get_cache_path(key)

        try:
            cache_data = {"timestamp": time.time(), "value": value}

            with open(cache_path, "w") as f:
                json.dump(cache_data, f)

            logger.debug(f"Cached value for key: {key}")
            return True
        except OSError as e:
            logger.warning(f"Error writing cache for key {key}: {e}")
            return False

    def invalidate(self, key: str) -> bool:
        """
        Invalidate a cache entry.

        Args:
            key: Cache key

        Returns:
            True if successful, False otherwise
        """
        cache_path = self._get_cache_path(key)

        if not cache_path.exists():
            return True

        try:
            os.remove(cache_path)
            logger.debug(f"Invalidated cache for key: {key}")
            return True
        except OSError as e:
            logger.warning(f"Error invalidating cache for key {key}: {e}")
            return False

    def clear(self) -> bool:
        """
        Clear all cache entries.

        Returns:
            True if successful, False otherwise
        """
        try:
            for cache_file in self.cache_dir.glob("*.json"):
                os.remove(cache_file)

            logger.debug("Cleared all cache entries")
            return True
        except OSError as e:
            logger.warning(f"Error clearing cache: {e}")
            return False


# Made with Bob
