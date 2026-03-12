"""Unit tests for health check endpoint."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from starlette.testclient import TestClient

from tim_mcp.server import mcp


def _resp(status_code, json_data=None):
    """Create a mock httpx response."""
    return httpx.Response(status_code, json=json_data or {})


def _mock_client(get_return=None, get_side_effect=None):
    """Build an AsyncMock that works as an async context manager with .client.get()."""
    mock = AsyncMock()
    mock.__aenter__.return_value = mock
    if get_side_effect:
        mock.client.get.side_effect = get_side_effect
    else:
        mock.client.get.return_value = get_return
    return mock


@pytest.fixture
def client():
    """Test client for the MCP HTTP app."""
    return TestClient(mcp.http_app(stateless_http=True))


class TestHealthEndpoint:
    """Tests for GET /health using the real route."""

    def test_healthy_when_all_deps_ok(self, client):
        """Both deps healthy -> 200, status 'healthy'."""
        gh = _mock_client(_resp(200, {"rate": {"remaining": 4999, "limit": 5000}}))
        tf = _mock_client(_resp(200))

        with (
            patch("tim_mcp.clients.github_client.GitHubClient", return_value=gh),
            patch("tim_mcp.clients.terraform_client.TerraformClient", return_value=tf),
        ):
            r = client.get("/health")

        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "healthy"
        assert body["dependencies"]["github"]["status"] == "healthy"
        assert body["dependencies"]["github"]["rate_limit_remaining"] == 4999
        assert body["dependencies"]["terraform_registry"]["status"] == "healthy"

    def test_degraded_github_401(self, client):
        """GitHub 401 -> 200, status 'degraded'."""
        gh = _mock_client(_resp(401, {"message": "Bad credentials"}))
        tf = _mock_client(_resp(200))

        with (
            patch("tim_mcp.clients.github_client.GitHubClient", return_value=gh),
            patch("tim_mcp.clients.terraform_client.TerraformClient", return_value=tf),
        ):
            r = client.get("/health")

        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "degraded"
        assert body["dependencies"]["github"]["status"] == "unhealthy"
        assert "Invalid or expired" in body["dependencies"]["github"]["error"]

    def test_github_low_rate_limit_warning(self, client):
        """GitHub low rate limit -> 200, healthy with warning field."""
        gh = _mock_client(_resp(200, {"rate": {"remaining": 5, "limit": 5000}}))
        tf = _mock_client(_resp(200))

        with (
            patch("tim_mcp.clients.github_client.GitHubClient", return_value=gh),
            patch("tim_mcp.clients.terraform_client.TerraformClient", return_value=tf),
        ):
            r = client.get("/health")

        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "healthy"
        assert body["dependencies"]["github"]["warning"] == "Low rate limit remaining"

    def test_degraded_terraform_unreachable(self, client):
        """Terraform Registry unreachable -> 200, status 'degraded'."""
        gh = _mock_client(_resp(200, {"rate": {"remaining": 4999, "limit": 5000}}))
        tf = _mock_client(get_side_effect=httpx.ConnectError("Connection refused"))

        with (
            patch("tim_mcp.clients.github_client.GitHubClient", return_value=gh),
            patch("tim_mcp.clients.terraform_client.TerraformClient", return_value=tf),
        ):
            r = client.get("/health")

        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "degraded"
        assert body["dependencies"]["terraform_registry"]["status"] == "unhealthy"
