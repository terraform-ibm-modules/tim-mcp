"""Unit tests for health check endpoint."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from starlette.testclient import TestClient

from tim_mcp.server import mcp

GH_PATCH = "tim_mcp.clients.github_client.GitHubClient"
TF_PATCH = "tim_mcp.clients.terraform_client.TerraformClient"


def _resp(status_code, json_data=None):
    return httpx.Response(status_code, json=json_data or {})


def _mock_client(get_return=None, get_side_effect=None):
    mock = AsyncMock()
    mock.__aenter__.return_value = mock
    if get_side_effect:
        mock.client.get.side_effect = get_side_effect
    else:
        mock.client.get.return_value = get_return
    return mock


@pytest.fixture
def client():
    return TestClient(mcp.http_app(stateless_http=True))


def _health(client, gh, tf):
    with patch(GH_PATCH, return_value=gh), patch(TF_PATCH, return_value=tf):
        return client.get("/health")


def _ok_gh():
    return _mock_client(_resp(200, {"rate": {"remaining": 4999, "limit": 5000}}))


def _ok_tf():
    return _mock_client(_resp(200))


class TestHealthEndpoint:
    def test_healthy(self, client):
        r = _health(client, _ok_gh(), _ok_tf())
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "healthy"
        assert body["dependencies"]["github"]["rate_limit_remaining"] == 4999
        assert body["dependencies"]["terraform_registry"]["status"] == "healthy"

    def test_degraded_github_401(self, client):
        r = _health(client, _mock_client(_resp(401)), _ok_tf())
        assert r.json()["status"] == "degraded"
        assert "Invalid or expired" in r.json()["dependencies"]["github"]["error"]

    def test_github_low_rate_limit_warning(self, client):
        gh = _mock_client(_resp(200, {"rate": {"remaining": 5, "limit": 5000}}))
        r = _health(client, gh, _ok_tf())
        assert r.json()["status"] == "healthy"
        assert (
            r.json()["dependencies"]["github"]["warning"] == "Low rate limit remaining"
        )

    def test_degraded_terraform_unreachable(self, client):
        tf = _mock_client(get_side_effect=httpx.ConnectError("Connection refused"))
        r = _health(client, _ok_gh(), tf)
        assert r.json()["status"] == "degraded"
        assert r.json()["dependencies"]["terraform_registry"]["status"] == "unhealthy"
