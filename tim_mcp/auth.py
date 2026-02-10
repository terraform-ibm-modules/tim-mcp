"""
Authentication for GitHub API requests.

Provides httpx.Auth implementations for GitHub App and PAT authentication,
plus a factory function to select the appropriate auth method from config.
"""

import asyncio
import base64
import time
from datetime import datetime

import httpx
import jwt

from .exceptions import ConfigurationError


class GitHubAppAuth(httpx.Auth):
    """httpx Auth that authenticates as a GitHub App installation.

    Creates short-lived JWTs to obtain installation access tokens,
    refreshing them automatically before expiry.
    """

    def __init__(
        self,
        app_id: str,
        private_key_b64: str,
        installation_id: str,
        github_base_url: str = "https://api.github.com",
        token_refresh_margin_seconds: int = 300,
    ):
        self.app_id = app_id
        self.installation_id = installation_id
        self.github_base_url = github_base_url.rstrip("/")
        self.token_refresh_margin_seconds = token_refresh_margin_seconds

        # Decode and validate private key in one step
        try:
            self._private_key = base64.b64decode(private_key_b64).decode("utf-8")
            jwt.encode({"test": True}, self._private_key, algorithm="RS256")
        except Exception as e:
            raise ConfigurationError(
                f"Invalid GitHub App private key: {e}",
                setting="github_app_private_key",
            ) from e

        self._token: str | None = None
        self._token_expires_at: float = 0
        self._lock = asyncio.Lock()

    def _create_jwt(self) -> str:
        """Create a JWT for GitHub App authentication (valid 10 minutes)."""
        now = int(time.time())
        return jwt.encode(
            {"iat": now - 60, "exp": now + 600, "iss": self.app_id},
            self._private_key,
            algorithm="RS256",
        )

    def _token_is_valid(self) -> bool:
        """Check if the current installation token is still fresh."""
        return time.time() < (self._token_expires_at - self.token_refresh_margin_seconds)

    async def _refresh_token(self) -> None:
        """Obtain a new installation access token from GitHub."""
        async with self._lock:
            if self._token_is_valid():
                return

            url = f"{self.github_base_url}/app/installations/{self.installation_id}/access_tokens"
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {self._create_jwt()}",
                        "Accept": "application/vnd.github+json",
                    },
                )
                response.raise_for_status()
                data = response.json()

            self._token = data["token"]
            expires_at = data.get("expires_at")
            self._token_expires_at = (
                datetime.fromisoformat(expires_at.replace("Z", "+00:00")).timestamp()
                if expires_at
                else time.time() + 3600
            )

    async def async_auth_flow(self, request: httpx.Request):
        if not self._token_is_valid():
            await self._refresh_token()
        request.headers["Authorization"] = f"Bearer {self._token}"
        yield request


class PATAuth(httpx.Auth):
    """httpx Auth that sets a Bearer token from a personal access token."""

    def __init__(self, token: str):
        self._token = token

    def auth_flow(self, request: httpx.Request):
        request.headers["Authorization"] = f"Bearer {self._token}"
        yield request


def create_github_auth(config) -> httpx.Auth | None:
    """Create the appropriate httpx.Auth from config.

    Priority: GitHub App > PAT > None (unauthenticated).
    """
    if (
        config.github_app_id
        and config.github_app_private_key
        and config.github_app_installation_id
    ):
        return GitHubAppAuth(
            app_id=config.github_app_id,
            private_key_b64=config.github_app_private_key,
            installation_id=config.github_app_installation_id,
            github_base_url=str(config.github_base_url),
        )
    if config.github_token:
        return PATAuth(config.github_token)
    return None
