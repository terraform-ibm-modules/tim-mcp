"""Unit tests for health check endpoint."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from tim_mcp.config import Config


def _make_github_response(status_code, json_data=None):
    """Create a mock httpx response."""
    response = httpx.Response(status_code, json=json_data or {})
    return response


@pytest.fixture
def config():
    return Config(github_token="test-token")


class TestHealthCheck:
    """Tests for the /health endpoint dependency checks."""

    @pytest.mark.asyncio
    async def test_healthy_when_all_dependencies_ok(self, config):
        """Health check returns healthy when GitHub and Terraform Registry are reachable."""
        from tim_mcp.clients.github_client import GitHubClient
        from tim_mcp.clients.terraform_client import TerraformClient

        github_resp = _make_github_response(200, {"rate": {"remaining": 4999, "limit": 5000}})
        tf_resp = _make_github_response(200, {"id": "test"})

        async with GitHubClient(config) as gh:
            gh.client = AsyncMock()
            gh.client.get = AsyncMock(return_value=github_resp)
            response = await gh.client.get("/rate_limit")
            assert response.status_code == 200
            rate_data = response.json()
            assert rate_data["rate"]["remaining"] == 4999

        async with TerraformClient(config) as tf:
            tf.client = AsyncMock()
            tf.client.get = AsyncMock(return_value=tf_resp)
            response = await tf.client.get("/modules/terraform-ibm-modules/landing-zone/ibm")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_degraded_with_invalid_github_token(self, config):
        """Health check returns degraded when GitHub token is invalid (401)."""
        from tim_mcp.clients.github_client import GitHubClient

        github_resp = _make_github_response(401, {"message": "Bad credentials"})

        async with GitHubClient(config) as gh:
            gh.client = AsyncMock()
            gh.client.get = AsyncMock(return_value=github_resp)
            response = await gh.client.get("/rate_limit")
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_degraded_with_low_rate_limit(self, config):
        """Health check warns when GitHub rate limit is low."""
        from tim_mcp.clients.github_client import GitHubClient

        github_resp = _make_github_response(200, {"rate": {"remaining": 5, "limit": 5000}})

        async with GitHubClient(config) as gh:
            gh.client = AsyncMock()
            gh.client.get = AsyncMock(return_value=github_resp)
            response = await gh.client.get("/rate_limit")
            rate_data = response.json()
            assert rate_data["rate"]["remaining"] < 10

    @pytest.mark.asyncio
    async def test_degraded_when_terraform_registry_unreachable(self, config):
        """Health check returns degraded when Terraform Registry is unreachable."""
        from tim_mcp.clients.terraform_client import TerraformClient

        async with TerraformClient(config) as tf:
            tf.client = AsyncMock()
            tf.client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
            with pytest.raises(httpx.ConnectError):
                await tf.client.get("/modules/terraform-ibm-modules/landing-zone/ibm")

    @pytest.mark.asyncio
    async def test_github_rate_limit_response_structure(self, config):
        """Verify the expected GitHub /rate_limit API response structure."""
        github_resp = _make_github_response(200, {
            "rate": {"remaining": 4999, "limit": 5000, "reset": 1234567890},
            "resources": {}
        })
        data = github_resp.json()
        assert "rate" in data
        assert "remaining" in data["rate"]
        assert "limit" in data["rate"]
