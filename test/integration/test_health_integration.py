"""Integration tests for health check - verifying real API rate limit behavior.

Per PR review (vburckhardt): verify the assumed behaviour of the APIs by
passing no token to bump into the unauthenticated rate limit.
"""

import os

import pytest

from tim_mcp.clients.github_client import GitHubClient
from tim_mcp.config import Config


@pytest.mark.integration
class TestGitHubRateLimitBehavior:
    """Verify GitHub API rate limit behavior with and without authentication."""

    @pytest.mark.asyncio
    async def test_unauthenticated_rate_limit(self):
        """Unauthenticated GitHub API calls have a 60 req/hr limit."""
        config = Config(github_token=None)
        async with GitHubClient(config) as gh:
            response = await gh.client.get("/rate_limit")
            assert response.status_code == 200
            rate = response.json()["rate"]
            assert rate["limit"] == 60

    @pytest.mark.asyncio
    async def test_authenticated_rate_limit(self):
        """Authenticated GitHub API calls have a 5000 req/hr limit."""
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            pytest.skip("GITHUB_TOKEN not set")
        config = Config(github_token=token)
        async with GitHubClient(config) as gh:
            response = await gh.client.get("/rate_limit")
            assert response.status_code == 200
            rate = response.json()["rate"]
            assert rate["limit"] == 5000
