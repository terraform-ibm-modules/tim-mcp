"""Tests for GitHub App configuration in tim_mcp.config."""

import os
from unittest.mock import patch

import pytest

from tim_mcp.config import Config, get_github_auth_headers, load_config


class TestGitHubAppConfigValidation:
    """Tests for all-or-nothing validation of GitHub App fields."""

    def test_all_fields_set(self):
        config = Config(
            github_app_id="12345",
            github_app_private_key="dGVzdA==",
            github_app_installation_id="67890",
        )
        assert config.github_app_id == "12345"
        assert config.github_app_installation_id == "67890"

    def test_no_fields_set(self):
        config = Config()
        assert config.github_app_id is None
        assert config.github_app_private_key is None
        assert config.github_app_installation_id is None

    def test_partial_fields_missing_id(self):
        with pytest.raises(ValueError, match="Missing.*github_app_id"):
            Config(
                github_app_private_key="dGVzdA==",
                github_app_installation_id="67890",
            )

    def test_partial_fields_missing_key(self):
        with pytest.raises(ValueError, match="Missing.*github_app_private_key"):
            Config(
                github_app_id="12345",
                github_app_installation_id="67890",
            )

    def test_partial_fields_missing_installation_id(self):
        with pytest.raises(ValueError, match="Missing.*github_app_installation_id"):
            Config(
                github_app_id="12345",
                github_app_private_key="dGVzdA==",
            )


class TestLoadConfigGitHubApp:
    """Tests for loading GitHub App env vars via load_config."""

    def test_loads_all_app_env_vars(self):
        env = {
            "GITHUB_APP_ID": "111",
            "GITHUB_APP_PRIVATE_KEY": "a2V5",
            "GITHUB_APP_INSTALLATION_ID": "222",
        }
        with patch.dict(os.environ, env, clear=False):
            config = load_config()
        assert config.github_app_id == "111"
        assert config.github_app_private_key == "a2V5"
        assert config.github_app_installation_id == "222"

    def test_no_app_env_vars(self):
        env_keys = ["GITHUB_APP_ID", "GITHUB_APP_PRIVATE_KEY", "GITHUB_APP_INSTALLATION_ID"]
        cleaned = {k: v for k, v in os.environ.items() if k not in env_keys}
        with patch.dict(os.environ, cleaned, clear=True):
            config = load_config()
        assert config.github_app_id is None


class TestGetGithubAuthHeaders:
    """Tests that get_github_auth_headers returns only non-auth headers."""

    def test_no_authorization_header(self):
        headers = get_github_auth_headers()
        assert "Authorization" not in headers
        assert headers["Accept"] == "application/vnd.github+json"
        assert headers["X-GitHub-Api-Version"] == "2022-11-28"
