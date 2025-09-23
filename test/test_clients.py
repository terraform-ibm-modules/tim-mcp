"""
Tests for the clients module.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tim_mcp.clients.github_client import GitHubClient
from tim_mcp.clients.terraform_client import TerraformClient
from tim_mcp.exceptions import ModuleNotFoundError


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

    @pytest.mark.asyncio
    async def test_get_latest_release(self, github_client, mock_cache):
        """Test getting latest release information."""
        # Setup
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "tag_name": "v1.2.3",
            "name": "Release v1.2.3",
            "published_at": "2023-01-01T00:00:00Z",
            "html_url": "https://github.com/terraform-ibm-modules/terraform-ibm-vpc/releases/tag/v1.2.3",
        }
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        github_client.client.get = AsyncMock(return_value=mock_response)

        # Execute
        result = await github_client.get_latest_release("terraform-ibm-modules", "terraform-ibm-vpc")

        # Verify
        expected_release = {
            "tag_name": "v1.2.3",
            "name": "Release v1.2.3",
            "published_at": "2023-01-01T00:00:00Z",
            "html_url": "https://github.com/terraform-ibm-modules/terraform-ibm-vpc/releases/tag/v1.2.3",
        }
        assert result == expected_release
        github_client.client.get.assert_called_once_with("/repos/terraform-ibm-modules/terraform-ibm-vpc/releases/latest")

    @pytest.mark.asyncio
    async def test_get_latest_release_not_found(self, github_client, mock_cache):
        """Test getting latest release when no releases exist."""
        # Setup
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status = MagicMock(side_effect=Exception("Not found"))
        github_client.client.get = AsyncMock(return_value=mock_response)

        # Execute and verify exception
        with pytest.raises(ModuleNotFoundError):
            await github_client.get_latest_release("terraform-ibm-modules", "no-releases")

    @pytest.mark.asyncio
    async def test_resolve_version_latest_with_release(self, github_client, mock_cache):
        """Test resolving 'latest' version to release tag."""
        # Setup - Mock get_latest_release to return a release
        github_client.get_latest_release = AsyncMock(
            return_value={
                "tag_name": "v2.1.0",
                "name": "Release v2.1.0",
            }
        )

        # Execute
        result = await github_client.resolve_version("terraform-ibm-modules", "terraform-ibm-vpc", "latest")

        # Verify
        assert result == "v2.1.0"
        github_client.get_latest_release.assert_called_once_with("terraform-ibm-modules", "terraform-ibm-vpc")

    @pytest.mark.asyncio
    async def test_resolve_version_latest_no_releases(self, github_client, mock_cache):
        """Test resolving 'latest' version when no releases exist (fallback to HEAD)."""
        from tim_mcp.exceptions import ModuleNotFoundError

        # Setup - Mock get_latest_release to raise ModuleNotFoundError
        github_client.get_latest_release = AsyncMock(
            side_effect=ModuleNotFoundError("test-repo", details={"reason": "No releases found"})
        )

        # Execute
        result = await github_client.resolve_version("terraform-ibm-modules", "terraform-ibm-vpc", "latest")

        # Verify
        assert result == "HEAD"
        github_client.get_latest_release.assert_called_once_with("terraform-ibm-modules", "terraform-ibm-vpc")

    @pytest.mark.asyncio
    async def test_resolve_version_specific_tag(self, github_client, mock_cache):
        """Test resolving specific version tag (should return as-is)."""
        # Execute
        result = await github_client.resolve_version("terraform-ibm-modules", "terraform-ibm-vpc", "v1.5.2")

        # Verify
        assert result == "v1.5.2"
        # Should not call get_latest_release for specific versions

    @pytest.mark.asyncio
    async def test_resolve_version_branch_name(self, github_client, mock_cache):
        """Test resolving branch name (should return as-is)."""
        # Execute
        result = await github_client.resolve_version("terraform-ibm-modules", "terraform-ibm-vpc", "main")

        # Verify
        assert result == "main"

    @pytest.mark.asyncio
    async def test_resolve_version_error_fallback(self, github_client, mock_cache):
        """Test resolving version with API error (fallback to HEAD)."""
        # Setup - Mock get_latest_release to raise generic error
        github_client.get_latest_release = AsyncMock(side_effect=Exception("API Error"))

        # Execute
        result = await github_client.resolve_version("terraform-ibm-modules", "terraform-ibm-vpc", "latest")

        # Verify
        assert result == "HEAD"
        github_client.get_latest_release.assert_called_once_with("terraform-ibm-modules", "terraform-ibm-vpc")

    def test_match_file_patterns_valid_patterns(self, github_client, mock_cache):
        """Test match_file_patterns with valid regex patterns."""
        # Test include patterns
        assert github_client.match_file_patterns("main.tf", include_patterns=[".*\\.tf$"])
        assert not github_client.match_file_patterns("main.py", include_patterns=[".*\\.tf$"])

        # Test exclude patterns
        assert not github_client.match_file_patterns("test_main.tf", exclude_patterns=[".*test.*"])
        assert github_client.match_file_patterns("main.tf", exclude_patterns=[".*test.*"])

        # Test combined patterns
        assert github_client.match_file_patterns("main.tf", include_patterns=[".*\\.tf$"], exclude_patterns=[".*test.*"])
        assert not github_client.match_file_patterns("test_main.tf", include_patterns=[".*\\.tf$"], exclude_patterns=[".*test.*"])

    def test_match_file_patterns_invalid_regex(self, github_client, mock_cache):
        """Test match_file_patterns with invalid regex patterns."""
        # Test invalid include patterns
        result = github_client.match_file_patterns("main.tf", include_patterns=["*", "*.tf", ".*\\.tf$"])
        # Should still match because the valid pattern ".*\\.tf$" matches
        assert result

        # Test all invalid include patterns
        result = github_client.match_file_patterns("main.tf", include_patterns=["*", "+", "?"])
        # Should return True because all patterns are invalid (default behavior)
        assert result

        # Test invalid exclude patterns
        result = github_client.match_file_patterns("main.tf", exclude_patterns=["*", "+"])
        # Should return True because invalid patterns are skipped
        assert result

        # Test mixed valid and invalid exclude patterns
        result = github_client.match_file_patterns("test_main.tf", exclude_patterns=["*", ".*test.*"])
        # Should return False because the valid exclude pattern matches
        assert not result

    def test_match_file_patterns_no_patterns(self, github_client, mock_cache):
        """Test match_file_patterns with no patterns (should include by default)."""
        assert github_client.match_file_patterns("any_file.txt")
        assert github_client.match_file_patterns("main.tf")

    def test_match_file_patterns_empty_patterns(self, github_client, mock_cache):
        """Test match_file_patterns with empty pattern lists."""
        assert github_client.match_file_patterns("main.tf", include_patterns=[], exclude_patterns=[])
        assert github_client.match_file_patterns("main.tf", include_patterns=None, exclude_patterns=None)


# Made with Bob
