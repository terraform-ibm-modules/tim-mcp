"""
Tests for the clients module.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tim_mcp.clients.github_client import GitHubClient
from tim_mcp.clients.terraform_client import TerraformClient


@pytest.fixture
def config():
    """Create a test configuration."""
    from tim_mcp.config import Config

    return Config()


@pytest.fixture
def mock_cache():
    """Create a mock cache."""
    mock_cache = MagicMock()
    mock_cache.get.return_value = None
    return mock_cache


class TestTerraformClient:
    """Tests for the TerraformClient class."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock requests session."""
        mock_session = MagicMock()
        return mock_session

    @pytest.fixture
    def terraform_client(self, config, mock_cache):
        """Create a TerraformClient instance with a mock cache."""
        with patch("httpx.AsyncClient") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session
            client = TerraformClient(config=config, cache=mock_cache)
            client.client = mock_session
            return client

    @pytest.mark.asyncio
    async def test_search_modules(self, terraform_client, mock_cache):
        """Test searching for modules."""
        # Setup
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "modules": [
                {
                    "id": "hashicorp/consul/aws",
                    "owner": "hashicorp",
                    "name": "consul",
                    "provider": "aws",
                },
                {
                    "id": "hashicorp/vault/aws",
                    "owner": "hashicorp",
                    "name": "vault",
                    "provider": "aws",
                },
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200
        terraform_client.client.get = AsyncMock(return_value=mock_response)

        # Execute
        result = await terraform_client.search_modules("consul")

        # Verify
        expected_data = {
            "modules": [
                {
                    "id": "hashicorp/consul/aws",
                    "owner": "hashicorp",
                    "name": "consul",
                    "provider": "aws",
                },
                {
                    "id": "hashicorp/vault/aws",
                    "owner": "hashicorp",
                    "name": "vault",
                    "provider": "aws",
                },
            ]
        }
        assert result == expected_data
        terraform_client.client.get.assert_called_once_with(
            "/modules/search",
            params={"q": "consul", "limit": 10, "offset": 0},
        )

    @pytest.mark.asyncio
    async def test_get_module_versions(self, terraform_client, mock_cache):
        """Test getting module versions."""
        # Setup
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "modules": [
                {"version": "1.0.0"},
                {"version": "1.1.0"},
                {"version": "1.2.0"},
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200
        terraform_client.client.get = AsyncMock(return_value=mock_response)

        # Execute
        result = await terraform_client.get_module_versions("hashicorp", "consul", "aws")

        # Verify
        assert result == ["1.0.0", "1.1.0", "1.2.0"]
        terraform_client.client.get.assert_called_once_with("/modules/hashicorp/consul/aws/versions")


class TestGitHubClient:
    """Tests for the GitHubClient class."""

    @pytest.fixture
    def github_client(self, config, mock_cache):
        """Create a GitHubClient instance with a mock cache."""
        with patch("httpx.AsyncClient") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session
            client = GitHubClient(config=config, cache=mock_cache)
            client.client = mock_session
            return client

    @pytest.mark.asyncio
    async def test_get_repository_info(self, github_client, mock_cache):
        """Test getting repository information."""
        # Setup
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "full_name": "hashicorp/terraform",
            "description": "Terraform infrastructure as code tool",
            "html_url": "https://github.com/hashicorp/terraform",
        }
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200
        github_client.client.get = AsyncMock(return_value=mock_response)

        # Execute
        result = await github_client.get_repository_info("hashicorp", "terraform")

        # Verify
        expected_info = {
            "full_name": "hashicorp/terraform",
            "description": "Terraform infrastructure as code tool",
            "html_url": "https://github.com/hashicorp/terraform",
        }
        assert result == expected_info
        github_client.client.get.assert_called_once_with("/repos/hashicorp/terraform")

    @pytest.mark.asyncio
    async def test_get_file_content(self, github_client, mock_cache):
        """Test getting content from a repository."""
        # Setup
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "name": "main.tf",
            "path": "main.tf",
            "content": "encoded_content",
            "encoding": "base64",
        }
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200
        github_client.client.get = AsyncMock(return_value=mock_response)

        # Execute
        result = await github_client.get_file_content("hashicorp", "terraform", "main.tf")

        # Verify
        expected_content = {
            "name": "main.tf",
            "path": "main.tf",
            "content": "encoded_content",
            "encoding": "base64",
        }
        assert result == expected_content
        github_client.client.get.assert_called_once_with(
            "/repos/hashicorp/terraform/contents/main.tf",
            params={},
        )

    @pytest.mark.asyncio
    async def test_get_directory_contents(self, github_client, mock_cache):
        """Test listing files in a repository."""
        # Setup
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"name": "main.tf", "path": "main.tf", "type": "file"},
            {"name": "variables.tf", "path": "variables.tf", "type": "file"},
            {"name": "outputs.tf", "path": "outputs.tf", "type": "file"},
        ]
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200
        github_client.client.get = AsyncMock(return_value=mock_response)

        # Execute
        result = await github_client.get_directory_contents("hashicorp", "terraform", "")

        # Verify
        expected_files = [
            {"name": "main.tf", "path": "main.tf", "type": "file"},
            {"name": "variables.tf", "path": "variables.tf", "type": "file"},
            {"name": "outputs.tf", "path": "outputs.tf", "type": "file"},
        ]
        assert result == expected_files
        github_client.client.get.assert_called_once_with("/repos/hashicorp/terraform/contents", params={})


# Made with Bob
