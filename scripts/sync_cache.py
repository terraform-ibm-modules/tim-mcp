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

# Concurrency limit + throttle to stay under GitHub's 5000 req/hour limit
# 5 concurrent * 2 req/module * 0.2s delay = ~50 req/sec max burst, well under limit
MAX_CONCURRENT = 5


async def sync_cache():
    """Pre-warm Redis cache with all module data."""
    print("Starting cache sync...")

    if not os.environ.get("GITHUB_TOKEN"):
        print("ERROR: GITHUB_TOKEN environment variable required")
        sys.exit(1)

    redis_url = os.environ.get("TIM_REDIS_URL", "redis://localhost:6379")
    config = load_config()
    redis = RedisCache(url=redis_url, ttl=3600, stale_ttl_multiplier=48)

    if not await redis.connect():
        print("ERROR: Failed to connect to Redis")
        sys.exit(1)

    try:
        async with (
            TerraformClient(config) as tf_client,
            GitHubClient(config) as gh_client,
        ):
            # Fetch all namespaces in parallel
            print("Fetching modules from all namespaces...")
            namespace_results = await asyncio.gather(
                *[tf_client.list_all_modules(ns) for ns in config.allowed_namespaces]
            )
            all_modules = [m for modules in namespace_results for m in modules]
            print(f"Total modules to process: {len(all_modules)}")

            # Process modules with controlled concurrency
            semaphore = asyncio.Semaphore(MAX_CONCURRENT)
            results = {"success": 0, "error": 0, "skipped": 0}

            async def process_module(module: dict) -> None:
                source = module.get("source", "")
                owner_repo = gh_client.parse_github_url(source)
                if not owner_repo:
                    results["skipped"] += 1
                    return

                owner, repo = owner_repo
                async with semaphore:
                    try:
                        # Fetch both in parallel, then cache
                        repo_info, tree = await asyncio.gather(
                            gh_client.get_repository_info(owner, repo),
                            gh_client.get_repository_tree(owner, repo),
                        )
                        await asyncio.gather(
                            redis.set(f"gh_repo_info_{owner}_{repo}", repo_info),
                            redis.set(f"gh_repo_tree_{owner}_{repo}_HEAD_True", tree),
                        )
                        results["success"] += 1
                        # Throttle to stay under GitHub's 5000 req/hour limit
                        await asyncio.sleep(0.2)
                    except Exception as e:
                        results["error"] += 1
                        print(f"  Error: {owner}/{repo}: {e}")

            # Process all modules concurrently (semaphore limits parallelism)
            await asyncio.gather(*[process_module(m) for m in all_modules])

            print("\nSync complete!")
            print(f"  Success: {results['success']}")
            print(f"  Errors: {results['error']}")
            print(f"  Skipped: {results['skipped']}")

    finally:
        await redis.close()


if __name__ == "__main__":
    asyncio.run(sync_cache())
