#!/usr/bin/env python3
"""
Daily cache sync script for TIM-MCP.

Pre-warms Redis cache with all module data to minimize GitHub API calls
during normal operation.

Usage:
    python scripts/sync_cache.py

Environment variables:
    GITHUB_TOKEN: Required for GitHub API access
    TIM_REDIS_URL: Redis connection URL (default: redis://localhost:6379)
"""

import asyncio
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from tim_mcp.clients.github_client import GitHubClient
from tim_mcp.clients.terraform_client import TerraformClient
from tim_mcp.config import load_config
from tim_mcp.utils.redis_cache import RedisCache


async def sync_cache():
    """Pre-warm Redis cache with all module data."""
    print("Starting cache sync...")

    # Validate environment
    if not os.environ.get("GITHUB_TOKEN"):
        print("ERROR: GITHUB_TOKEN environment variable required")
        sys.exit(1)

    redis_url = os.environ.get("TIM_REDIS_URL", "redis://localhost:6379")

    # Initialize
    config = load_config()
    redis = RedisCache(url=redis_url, ttl=3600, stale_ttl_multiplier=48)

    connected = await redis.connect()
    if not connected:
        print("ERROR: Failed to connect to Redis")
        sys.exit(1)

    try:
        async with (
            TerraformClient(config) as tf_client,
            GitHubClient(config) as gh_client,
        ):
            # Fetch all modules for each namespace
            all_modules = []
            for namespace in config.allowed_namespaces:
                print(f"Fetching modules from {namespace}...")
                modules = await tf_client.list_all_modules(namespace)
                all_modules.extend(modules)
                print(f"  Found {len(modules)} modules in {namespace}")

            print(f"Total modules to process: {len(all_modules)}")

            # Pre-warm cache for each module
            success_count = 0
            error_count = 0
            skipped_count = 0

            for i, module in enumerate(all_modules):
                module_id = module.get("id", "")
                source = module.get("source", "")

                try:
                    # Parse GitHub URL
                    owner_repo = gh_client.parse_github_url(source)
                    if not owner_repo:
                        skipped_count += 1
                        continue

                    owner, repo = owner_repo

                    # Fetch and cache repo info
                    repo_info = await gh_client.get_repository_info(owner, repo)
                    await redis.set(f"gh_repo_info_{owner}_{repo}", repo_info)

                    # Fetch and cache repo tree
                    tree = await gh_client.get_repository_tree(owner, repo)
                    await redis.set(f"gh_repo_tree_{owner}_{repo}_HEAD_True", tree)

                    success_count += 1

                    # Rate limit: ~2 requests per module, stay under 5000/hour
                    # With 100 modules = 200 requests, safe margin
                    await asyncio.sleep(0.5)

                except Exception as e:
                    error_count += 1
                    print(f"  Error caching {module_id}: {e}")

                # Progress
                if (i + 1) % 10 == 0:
                    print(f"  Progress: {i + 1}/{len(all_modules)}")

            print("\nSync complete!")
            print(f"  Success: {success_count}")
            print(f"  Errors: {error_count}")
            print(f"  Skipped (no GitHub URL): {skipped_count}")

            # Print stats
            stats = await redis.get_stats()
            print(f"  Redis keys: {stats.get('keys', 'unknown')}")

    finally:
        await redis.close()


if __name__ == "__main__":
    asyncio.run(sync_cache())
