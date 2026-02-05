"""
Tests for the tools module.
"""

from unittest.mock import MagicMock, patch

import pytest

from tim_mcp.tools.github import GitHubTools
from tim_mcp.tools.registry import RegistryTools


class TestRegistryTools:
    """Tests for the RegistryTools class."""

    @pytest.fixture
    def mock_terraform_client(self):
        """Create a mock Terraform client."""
        mock_client = MagicMock()
        return mock_client

    @pytest.fixture
    def registry_tools(self, mock_terraform_client):
        """Create a RegistryTools instance with a mock client."""
        return RegistryTools(client=mock_terraform_client)

    def test_search_modules(self, registry_tools, mock_terraform_client):
        """Test searching for modules."""
        # Setup
        mock_modules = [
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
        mock_terraform_client.search_modules.return_value = mock_modules

        # Execute
        result = registry_tools.search_modules("consul")

        # Verify
        assert result == mock_modules
        mock_terraform_client.search_modules.assert_called_once_with("consul", None)

    def test_get_module_versions(self, registry_tools, mock_terraform_client):
        """Test getting module versions."""
        # Setup
        mock_versions = ["1.0.0", "1.1.0", "1.2.0"]
        mock_terraform_client.get_module_versions.return_value = mock_versions

        # Execute
        result = registry_tools.get_module_versions("hashicorp", "consul")

        # Verify
        assert result == mock_versions
        mock_terraform_client.get_module_versions.assert_called_once_with(
            "hashicorp", "consul"
        )

    def test_get_provider_info(self, registry_tools, mock_terraform_client):
        """Test getting provider information."""
        # Setup
        mock_info = {"id": "hashicorp/aws", "name": "aws", "namespace": "hashicorp"}
        mock_terraform_client.get_provider_info.return_value = mock_info

        # Execute
        result = registry_tools.get_provider_info("hashicorp", "aws")

        # Verify
        assert result == mock_info
        mock_terraform_client.get_provider_info.assert_called_once_with(
            "hashicorp", "aws"
        )


class TestGitHubTools:
    """Tests for the GitHubTools class."""

    @pytest.fixture
    def mock_github_client(self):
        """Create a mock GitHub client."""
        mock_client = MagicMock()
        return mock_client

    @pytest.fixture
    def github_tools(self, mock_github_client):
        """Create a GitHubTools instance with a mock client."""
        return GitHubTools(client=mock_github_client)

    def test_clone_repository(self, github_tools, mock_github_client):
        """Test cloning a repository."""
        # Setup
        mock_github_client.clone_repository.return_value = True

        # Execute
        result = github_tools.clone_repository(
            "https://github.com/hashicorp/terraform", "/tmp/terraform"
        )

        # Verify
        assert result is True
        mock_github_client.clone_repository.assert_called_once_with(
            "https://github.com/hashicorp/terraform", "/tmp/terraform", None
        )

    def test_fetch_module_source(self, github_tools, mock_github_client):
        """Test fetching module source."""
        # Setup
        mock_source = {"path": "modules/consul", "content": "module content"}
        mock_github_client.get_content.return_value = mock_source

        # Execute
        result = github_tools.fetch_module_source(
            "hashicorp", "terraform", "modules/consul"
        )

        # Verify
        assert result == mock_source
        mock_github_client.get_content.assert_called_once_with(
            "hashicorp", "terraform", "modules/consul", None
        )

    def test_list_terraform_files(self, github_tools, mock_github_client):
        """Test listing Terraform files."""
        # Setup
        mock_files = ["main.tf", "variables.tf", "outputs.tf"]
        mock_github_client.list_files.return_value = [
            {"name": "main.tf", "path": "main.tf", "type": "file"},
            {"name": "variables.tf", "path": "variables.tf", "type": "file"},
            {"name": "outputs.tf", "path": "outputs.tf", "type": "file"},
            {"name": "README.md", "path": "README.md", "type": "file"},
        ]

        # Execute
        with patch.object(
            github_tools, "list_terraform_files", return_value=mock_files
        ):
            result = github_tools.list_terraform_files("hashicorp", "terraform")

        # Verify
        assert result == mock_files


# Made with Bob
