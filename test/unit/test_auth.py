"""Tests for tim_mcp.auth module."""

import asyncio
import base64
import time
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from tim_mcp.auth import GitHubAppAuth, PATAuth, create_github_auth
from tim_mcp.exceptions import ConfigurationError

# Generate a test RSA key pair once at module level
_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
TEST_KEY_B64 = base64.b64encode(
    _key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
).decode()
TEST_PUBLIC_KEY_PEM = _key.public_key().public_bytes(
    serialization.Encoding.PEM,
    serialization.PublicFormat.SubjectPublicKeyInfo,
).decode()


def _make_auth(**overrides) -> GitHubAppAuth:
    defaults = {"app_id": "12345", "private_key_b64": TEST_KEY_B64, "installation_id": "67890"}
    return GitHubAppAuth(**(defaults | overrides))


@contextmanager
def _mock_github_token_response(token="ghs_test", expires="2099-01-01T00:00:00Z"):
    """Patch httpx.AsyncClient to return a fake installation token."""
    resp = MagicMock()
    resp.json.return_value = {"token": token, "expires_at": expires}
    resp.raise_for_status = MagicMock()
    with patch("tim_mcp.auth.httpx.AsyncClient") as cls:
        client = AsyncMock()
        client.post.return_value = resp
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        cls.return_value = client
        yield client


class TestGitHubAppAuth:
    def test_init_valid_key(self):
        auth = _make_auth()
        assert auth.app_id == "12345"

    def test_init_invalid_base64(self):
        with pytest.raises(ConfigurationError, match="Invalid GitHub App private key"):
            _make_auth(private_key_b64="not-valid-base64!!!")

    def test_init_invalid_key_content(self):
        with pytest.raises(ConfigurationError, match="Invalid GitHub App private key"):
            _make_auth(private_key_b64=base64.b64encode(b"not a PEM").decode())

    def test_create_jwt(self):
        token = _make_auth()._create_jwt()
        decoded = jwt.decode(token, TEST_PUBLIC_KEY_PEM, algorithms=["RS256"])
        assert decoded["iss"] == "12345"

    def test_token_is_valid_fresh(self):
        auth = _make_auth()
        auth._token, auth._token_expires_at = "tok", time.time() + 3600
        assert auth._token_is_valid() is True

    def test_token_is_valid_expired(self):
        auth = _make_auth()
        auth._token, auth._token_expires_at = "tok", time.time() + 100
        assert auth._token_is_valid() is False

    def test_token_is_valid_when_none(self):
        assert _make_auth()._token_is_valid() is False

    @pytest.mark.asyncio
    async def test_refresh_token(self):
        auth = _make_auth()
        with _mock_github_token_response("ghs_123"):
            await auth._refresh_token()
        assert auth._token == "ghs_123"
        assert auth._token_expires_at > time.time()

    @pytest.mark.asyncio
    async def test_concurrent_refresh_only_calls_once(self):
        auth = _make_auth()
        call_count = 0

        async def mock_post(*_a, **_kw):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.05)
            resp = MagicMock()
            resp.json.return_value = {"token": "ghs_c", "expires_at": "2099-01-01T00:00:00Z"}
            resp.raise_for_status = MagicMock()
            return resp

        with patch("tim_mcp.auth.httpx.AsyncClient") as cls:
            client = AsyncMock()
            client.post = mock_post
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            cls.return_value = client
            await asyncio.gather(auth._refresh_token(), auth._refresh_token())

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_auth_flow_sets_header(self):
        auth = _make_auth()
        auth._token, auth._token_expires_at = "ghs_pre", time.time() + 3600
        request = httpx.Request("GET", "https://api.github.com/test")
        modified = await auth.async_auth_flow(request).__anext__()
        assert modified.headers["Authorization"] == "Bearer ghs_pre"

    @pytest.mark.asyncio
    async def test_auth_flow_refreshes_expired_token(self):
        auth = _make_auth()
        auth._token_expires_at = 0
        with _mock_github_token_response("ghs_new"):
            request = httpx.Request("GET", "https://api.github.com/test")
            modified = await auth.async_auth_flow(request).__anext__()
        assert modified.headers["Authorization"] == "Bearer ghs_new"


class TestPATAuth:
    def test_sets_bearer_header(self):
        request = httpx.Request("GET", "https://api.github.com/test")
        modified = next(PATAuth("ghp_tok").auth_flow(request))
        assert modified.headers["Authorization"] == "Bearer ghp_tok"


class TestCreateGithubAuth:
    def _config(self, **fields):
        cfg = MagicMock()
        defaults = {
            "github_app_id": None, "github_app_private_key": None,
            "github_app_installation_id": None, "github_token": None,
            "github_base_url": "https://api.github.com",
        }
        for k, v in (defaults | fields).items():
            setattr(cfg, k, v)
        return cfg

    def test_github_app_preferred_over_pat(self):
        cfg = self._config(
            github_app_id="1", github_app_private_key=TEST_KEY_B64,
            github_app_installation_id="2", github_token="ghp_x",
        )
        assert isinstance(create_github_auth(cfg), GitHubAppAuth)

    def test_pat_fallback(self):
        assert isinstance(create_github_auth(self._config(github_token="ghp_x")), PATAuth)

    def test_no_auth(self):
        assert create_github_auth(self._config()) is None
