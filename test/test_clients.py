"""
Tests for the clients module.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from tim_mcp.clients.github_client import GitHubClient
from tim_mcp.clients.terraform_client import TerraformClient, is_prerelease_version
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

    def test_is_prerelease_version_with_beta(self):
        """Test identifying beta versions as pre-release."""
        assert is_prerelease_version("1.0.0-beta") is True
        assert is_prerelease_version("2.1.0-beta.1") is True

    def test_is_prerelease_version_with_alpha(self):
        """Test identifying alpha versions as pre-release."""
        assert is_prerelease_version("1.0.0-alpha") is True
        assert is_prerelease_version("3.2.1-alpha.2") is True

    def test_is_prerelease_version_with_rc(self):
        """Test identifying release candidate versions as pre-release."""
        assert is_prerelease_version("1.0.0-rc") is True
        assert is_prerelease_version("2.0.0-rc.1") is True

    def test_is_prerelease_version_with_draft(self):
        """Test identifying draft versions as pre-release."""
        assert is_prerelease_version("2.0.1-draft") is True
        assert (
            is_prerelease_version("2.0.1-draft-addons") is True
        )  # Real example from issue #20

    def test_is_prerelease_version_stable(self):
        """Test that stable versions are not identified as pre-release."""
        assert is_prerelease_version("1.0.0") is False
        assert is_prerelease_version("2.5.3") is False
        assert is_prerelease_version("10.20.30") is False

    def test_is_prerelease_version_edge_cases(self):
        """Test edge cases for version identification."""
        # Version with metadata but no pre-release identifier
        assert is_prerelease_version("1.0.0+build.123") is False
        # Empty string
        assert is_prerelease_version("") is False
        # Invalid format
        assert is_prerelease_version("invalid") is False

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
        # Setup - use correct nested API structure
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "modules": [
                {
                    "versions": [
                        {"version": "1.0.0"},
                        {"version": "1.1.0"},
                        {"version": "1.2.0"},
                    ]
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200
        terraform_client.client.get = AsyncMock(return_value=mock_response)

        # Execute
        result = await terraform_client.get_module_versions(
            "hashicorp", "consul", "aws"
        )

        # Verify - sorted in descending order (latest first)
        assert result == ["1.2.0", "1.1.0", "1.0.0"]
        terraform_client.client.get.assert_called_once_with(
            "/modules/hashicorp/consul/aws/versions"
        )

    @pytest.mark.asyncio
    async def test_get_module_versions_filters_prerelease(
        self, terraform_client, mock_cache
    ):
        """Test that pre-release versions are filtered out."""
        # Setup - mix of stable and pre-release versions with correct nested structure
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "modules": [
                {
                    "versions": [
                        {"version": "1.0.0"},
                        {"version": "1.1.0-beta"},
                        {"version": "1.2.0"},
                        {"version": "2.0.0-draft"},
                        {
                            "version": "2.0.1-draft-addons"
                        },  # Real example from issue #20
                        {"version": "2.1.0-rc.1"},
                        {"version": "2.2.0"},
                        {"version": "3.0.0-alpha"},
                    ]
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200
        terraform_client.client.get = AsyncMock(return_value=mock_response)

        # Execute
        result = await terraform_client.get_module_versions(
            "terraform-ibm-modules", "db2-cloud", "ibm"
        )

        # Verify - only stable versions returned, sorted descending (latest first)
        assert result == ["2.2.0", "1.2.0", "1.0.0"]
        terraform_client.client.get.assert_called_once_with(
            "/modules/terraform-ibm-modules/db2-cloud/ibm/versions"
        )

    @pytest.mark.asyncio
    async def test_get_module_versions_all_prerelease(
        self, terraform_client, mock_cache
    ):
        """Test behavior when all versions are pre-release."""
        # Setup - only pre-release versions with correct nested structure
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "modules": [
                {
                    "versions": [
                        {"version": "1.0.0-beta"},
                        {"version": "1.1.0-alpha"},
                        {"version": "2.0.0-rc.1"},
                    ]
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200
        terraform_client.client.get = AsyncMock(return_value=mock_response)

        # Execute
        result = await terraform_client.get_module_versions(
            "terraform-ibm-modules", "test-module", "ibm"
        )

        # Verify - empty list when all are pre-release
        assert result == []
        terraform_client.client.get.assert_called_once_with(
            "/modules/terraform-ibm-modules/test-module/ibm/versions"
        )


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
        result = await github_client.get_file_content(
            "hashicorp", "terraform", "main.tf"
        )

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
        result = await github_client.get_directory_contents(
            "hashicorp", "terraform", ""
        )

        # Verify
        expected_files = [
            {"name": "main.tf", "path": "main.tf", "type": "file"},
            {"name": "variables.tf", "path": "variables.tf", "type": "file"},
            {"name": "outputs.tf", "path": "outputs.tf", "type": "file"},
        ]
        assert result == expected_files
        github_client.client.get.assert_called_once_with(
            "/repos/hashicorp/terraform/contents", params={}
        )

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
        result = await github_client.get_latest_release(
            "terraform-ibm-modules", "terraform-ibm-vpc"
        )

        # Verify
        expected_release = {
            "tag_name": "v1.2.3",
            "name": "Release v1.2.3",
            "published_at": "2023-01-01T00:00:00Z",
            "html_url": "https://github.com/terraform-ibm-modules/terraform-ibm-vpc/releases/tag/v1.2.3",
        }
        assert result == expected_release
        github_client.client.get.assert_called_once_with(
            "/repos/terraform-ibm-modules/terraform-ibm-vpc/releases/latest"
        )

    @pytest.mark.asyncio
    async def test_get_latest_release_not_found(self, github_client, mock_cache):
        """Test getting latest release when no releases exist."""
        # Setup
        mock_request = MagicMock()
        mock_request.url = "https://api.github.com/repos/terraform-ibm-modules/no-releases/releases/latest"

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"

        http_error = httpx.HTTPStatusError(
            "404 Client Error", request=mock_request, response=mock_response
        )
        mock_response.raise_for_status = MagicMock(side_effect=http_error)
        github_client.client.get = AsyncMock(return_value=mock_response)

        # Execute and verify exception
        with pytest.raises(ModuleNotFoundError):
            await github_client.get_latest_release(
                "terraform-ibm-modules", "no-releases"
            )

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
        result = await github_client.resolve_version(
            "terraform-ibm-modules", "terraform-ibm-vpc", "latest"
        )

        # Verify
        assert result == "v2.1.0"
        github_client.get_latest_release.assert_called_once_with(
            "terraform-ibm-modules", "terraform-ibm-vpc"
        )

    @pytest.mark.asyncio
    async def test_resolve_version_latest_no_releases(self, github_client, mock_cache):
        """Test resolving 'latest' version when no releases exist (fallback to HEAD)."""
        from tim_mcp.exceptions import ModuleNotFoundError

        # Setup - Mock get_latest_release to raise ModuleNotFoundError
        github_client.get_latest_release = AsyncMock(
            side_effect=ModuleNotFoundError(
                "test-repo", details={"reason": "No releases found"}
            )
        )

        # Execute
        result = await github_client.resolve_version(
            "terraform-ibm-modules", "terraform-ibm-vpc", "latest"
        )

        # Verify
        assert result == "HEAD"
        github_client.get_latest_release.assert_called_once_with(
            "terraform-ibm-modules", "terraform-ibm-vpc"
        )

    @pytest.mark.asyncio
    async def test_resolve_version_specific_tag(self, github_client, mock_cache):
        """Test resolving specific version tag (should return as-is)."""
        # Execute
        result = await github_client.resolve_version(
            "terraform-ibm-modules", "terraform-ibm-vpc", "v1.5.2"
        )

        # Verify
        assert result == "v1.5.2"
        # Should not call get_latest_release for specific versions

    @pytest.mark.asyncio
    async def test_resolve_version_branch_name(self, github_client, mock_cache):
        """Test resolving branch name (should return as-is)."""
        # Execute
        result = await github_client.resolve_version(
            "terraform-ibm-modules", "terraform-ibm-vpc", "main"
        )

        # Verify
        assert result == "main"

    @pytest.mark.asyncio
    async def test_resolve_version_error_fallback(self, github_client, mock_cache):
        """Test resolving version with API error (fallback to HEAD)."""
        # Setup - Mock get_latest_release to raise generic error
        github_client.get_latest_release = AsyncMock(side_effect=Exception("API Error"))

        # Execute
        result = await github_client.resolve_version(
            "terraform-ibm-modules", "terraform-ibm-vpc", "latest"
        )

        # Verify
        assert result == "HEAD"
        github_client.get_latest_release.assert_called_once_with(
            "terraform-ibm-modules", "terraform-ibm-vpc"
        )

    def test_match_file_patterns_valid_patterns(self, github_client, mock_cache):
        """Test match_file_patterns with valid glob patterns."""
        # Test include patterns
        assert github_client.match_file_patterns("main.tf", include_patterns=["*.tf"])
        assert not github_client.match_file_patterns(
            "main.py", include_patterns=["*.tf"]
        )

        # Test exclude patterns
        assert not github_client.match_file_patterns(
            "test_main.tf", exclude_patterns=["*test*"]
        )
        assert github_client.match_file_patterns("main.tf", exclude_patterns=["*test*"])

        # Test combined patterns
        assert github_client.match_file_patterns(
            "main.tf", include_patterns=["*.tf"], exclude_patterns=["*test*"]
        )
        assert not github_client.match_file_patterns(
            "test_main.tf", include_patterns=["*.tf"], exclude_patterns=["*test*"]
        )

    def test_match_file_patterns_complex_globs(self, github_client, mock_cache):
        """Test match_file_patterns with complex glob patterns."""
        # Test recursive patterns
        assert github_client.match_file_patterns(
            "examples/basic/main.tf", include_patterns=["**/*.tf"]
        )
        assert not github_client.match_file_patterns(
            "main.py", include_patterns=["**/*.tf"]
        )

        # Test directory-specific patterns
        assert github_client.match_file_patterns(
            "examples/basic/main.tf", include_patterns=["examples/**/*.tf"]
        )
        assert not github_client.match_file_patterns(
            "modules/vpc/main.tf", include_patterns=["examples/**/*.tf"]
        )

        # Test multiple include patterns
        result = github_client.match_file_patterns(
            "main.tf", include_patterns=["*.tf", "*.md"]
        )
        assert result

        result = github_client.match_file_patterns(
            "README.md", include_patterns=["*.tf", "*.md"]
        )
        assert result

        result = github_client.match_file_patterns(
            "script.py", include_patterns=["*.tf", "*.md"]
        )
        assert not result

    def test_match_file_patterns_no_patterns(self, github_client, mock_cache):
        """Test match_file_patterns with no patterns (should include by default)."""
        assert github_client.match_file_patterns("any_file.txt")
        assert github_client.match_file_patterns("main.tf")

    def test_match_file_patterns_empty_patterns(self, github_client, mock_cache):
        """Test match_file_patterns with empty pattern lists."""
        assert github_client.match_file_patterns(
            "main.tf", include_patterns=[], exclude_patterns=[]
        )
        assert github_client.match_file_patterns(
            "main.tf", include_patterns=None, exclude_patterns=None
        )

    def test_match_file_patterns_bug_regression(self, github_client, mock_cache):
        """Regression test for specific bug scenario reported by user.

        Tests the exact scenario: filtering .tf files in examples/basic directory
        with the pattern ["*.tf"]. This previously failed when patterns were
        treated as regex instead of glob patterns.
        """
        # Test files that would be in examples/basic directory
        test_files = [
            "examples/basic/main.tf",
            "examples/basic/variables.tf",
            "examples/basic/outputs.tf",
            "examples/basic/provider.tf",
            "examples/basic/version.tf",
            "examples/basic/README.md",
            "examples/basic/catalogValidationValues.json.template",
        ]

        include_pattern = ["*.tf"]

        # All .tf files should match
        tf_files = [f for f in test_files if f.endswith(".tf")]
        for tf_file in tf_files:
            assert github_client.match_file_patterns(tf_file, include_pattern, None), (
                f"{tf_file} should match pattern {include_pattern}"
            )

        # Non-.tf files should NOT match
        non_tf_files = [f for f in test_files if not f.endswith(".tf")]
        for non_tf_file in non_tf_files:
            assert not github_client.match_file_patterns(
                non_tf_file, include_pattern, None
            ), f"{non_tf_file} should NOT match pattern {include_pattern}"

        # Verify we found the expected number of matches
        matches = [
            f
            for f in test_files
            if github_client.match_file_patterns(f, include_pattern, None)
        ]
        assert len(matches) == 5, f"Expected 5 .tf files, got {len(matches)}: {matches}"


# Made with Bob
