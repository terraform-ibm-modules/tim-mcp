"""
Tests for the list_content tool.

This module tests the list_content implementation following TDD methodology.
Tests cover successful content listing, error handling, README parsing,
and path categorization logic.
"""

from unittest.mock import AsyncMock, patch

import pytest

from tim_mcp.config import Config
from tim_mcp.exceptions import (
    GitHubError,
    ModuleNotFoundError,
    RateLimitError,
    ValidationError,
)
from tim_mcp.tools.list_content import list_content_impl
from tim_mcp.types import ListContentRequest


class TestListContentImpl:
    """Tests for the list_content implementation function."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock config."""
        config = Config()
        config.github_token = "fake_token"
        return config

    @pytest.fixture
    def mock_github_client(self):
        """Create a mock GitHub client."""
        client = AsyncMock()
        return client

    @pytest.fixture
    def sample_tree_response(self):
        """Sample GitHub tree API response."""
        return [
            {"path": "README.md", "type": "blob", "mode": "100644"},
            {"path": "main.tf", "type": "blob", "mode": "100644"},
            {"path": "variables.tf", "type": "blob", "mode": "100644"},
            {"path": "outputs.tf", "type": "blob", "mode": "100644"},
            {"path": "examples", "type": "tree", "mode": "040000"},
            {"path": "examples/basic", "type": "tree", "mode": "040000"},
            {"path": "examples/basic/README.md", "type": "blob", "mode": "100644"},
            {"path": "examples/basic/main.tf", "type": "blob", "mode": "100644"},
            {"path": "examples/complete", "type": "tree", "mode": "040000"},
            {"path": "examples/complete/README.md", "type": "blob", "mode": "100644"},
            {"path": "modules", "type": "tree", "mode": "040000"},
            {"path": "modules/landing-zone-vpc", "type": "tree", "mode": "040000"},
            {
                "path": "modules/landing-zone-vpc/README.md",
                "type": "blob",
                "mode": "100644",
            },
        ]

    @pytest.fixture
    def sample_readme_content(self):
        """Sample README file content."""
        return {
            "": {
                "content": (
                    "# VPC Module\n\nMain VPC module for creating IBM Cloud VPC resources with subnets, "
                    "security groups, and routing tables."
                ),
                "decoded_content": (
                    "# VPC Module\n\nMain VPC module for creating IBM Cloud VPC resources with subnets, "
                    "security groups, and routing tables."
                ),
            },
            "examples/basic/README.md": {
                "content": "encoded_content",
                "decoded_content": (
                    "# Basic VPC Example\n\nSingle zone VPC for development environments with minimal configuration."
                ),
            },
            "examples/complete/README.md": {
                "content": "encoded_content",
                "decoded_content": (
                    "# Complete VPC Example\n\nMulti-zone production VPC with load balancers, floating IPs, "
                    "and advanced networking features."
                ),
            },
            "modules/landing-zone-vpc/README.md": {
                "content": "encoded_content",
                "decoded_content": (
                    "# Landing Zone VPC\n\nEnhanced VPC configuration with landing zone patterns and security defaults."
                ),
            },
        }

    @pytest.fixture
    def sample_repo_info(self):
        """Sample repository information."""
        return {
            "name": "terraform-ibm-vpc",
            "full_name": "terraform-ibm-modules/terraform-ibm-vpc",
            "default_branch": "main",
            "html_url": "https://github.com/terraform-ibm-modules/terraform-ibm-vpc",
        }

    @pytest.mark.asyncio
    async def test_list_content_success(
        self,
        mock_config,
        mock_github_client,
        sample_tree_response,
        sample_readme_content,
        sample_repo_info,
    ):
        """Test successful content listing using Registry API."""
        # Setup
        request = ListContentRequest(module_id="terraform-ibm-modules/vpc/ibm")

        # Mock GitHub for solutions lookup
        mock_github_client.resolve_version.return_value = "main"
        mock_github_client.get_repository_tree.return_value = sample_tree_response

        async def mock_get_file_content(owner, repo, path, ref="HEAD"):
            if path in sample_readme_content:
                return sample_readme_content[path]
            raise ModuleNotFoundError(f"{owner}/{repo}/{path}")

        mock_github_client.get_file_content.side_effect = mock_get_file_content

        # Execute
        with patch("tim_mcp.tools.list_content.GitHubClient") as MockGitHubClient:
            with patch("tim_mcp.tools.list_content.TerraformClient") as MockTerraformClient:
                MockGitHubClient.return_value = mock_github_client
                mock_github_client.client = AsyncMock()
                mock_github_client.client.aclose = AsyncMock()

                # Mock TerraformClient
                mock_terraform_client = AsyncMock()
                MockTerraformClient.return_value = mock_terraform_client
                mock_terraform_client.client = AsyncMock()
                mock_terraform_client.client.aclose = AsyncMock()

                # Return structure from Registry
                mock_terraform_client.get_module_structure.return_value = {
                    "version": "main",
                    "root": {
                        "readme": "# VPC Module\n\nMain VPC module for creating IBM Cloud VPC resources with subnets."
                    },
                    "examples": [
                        {
                            "path": "examples/basic",
                            "readme": "# Basic Example\n\nSingle zone VPC for development environments.",
                        },
                        {
                            "path": "examples/complete",
                            "readme": "# Complete Example\n\nMulti-zone production VPC.",
                        },
                    ],
                    "submodules": [
                        {
                            "path": "modules/landing-zone-vpc",
                            "readme": "# Landing Zone VPC\n\nEnhanced VPC configuration.",
                        }
                    ],
                }

                result = await list_content_impl(request, mock_config)

        # Verify
        assert "# terraform-ibm-modules/vpc/ibm - Available Content" in result
        assert "**Version:** main" in result

        # Check root module section
        assert "## Root Module" in result
        assert "**Path:** `` (empty string)" in result
        assert "Main VPC module for creating IBM Cloud VPC resources" in result

        # Check examples section
        assert "## Examples" in result
        assert "**Path:** `examples/basic`" in result
        assert "Single zone VPC for development" in result
        assert "**Path:** `examples/complete`" in result
        assert "Multi-zone production VPC" in result

        # Check submodules section
        assert "## Submodules" in result
        assert "**Path:** `modules/landing-zone-vpc`" in result
        assert "Enhanced VPC configuration" in result

    @pytest.mark.asyncio
    async def test_list_content_with_specific_version(
        self,
        mock_config,
        mock_github_client,
        sample_tree_response,
        sample_readme_content,
        sample_repo_info,
    ):
        """Test content listing with specific version tag."""
        # Setup
        request = ListContentRequest(module_id="terraform-ibm-modules/vpc/ibm/v5.1.0")

        mock_github_client.get_repository_info.return_value = sample_repo_info
        mock_github_client.resolve_version.return_value = "v5.1.0"
        mock_github_client.get_repository_tree.return_value = sample_tree_response

        async def mock_get_file_content(owner, repo, path, ref="HEAD"):
            if path == "README.md":
                return sample_readme_content[""]
            return sample_readme_content.get(path, {})

        mock_github_client.get_file_content.side_effect = mock_get_file_content

        # Execute
        with patch("tim_mcp.tools.list_content.GitHubClient") as MockGitHubClient:
            MockGitHubClient.return_value = mock_github_client
            mock_github_client.client = AsyncMock()
            mock_github_client.client.aclose = AsyncMock()
            result = await list_content_impl(request, mock_config)

        # Verify
        assert "**Version:** v5.1.0" in result

        # Verify GitHub client called with specific version
        mock_github_client.get_repository_tree.assert_called_once_with(
            "terraform-ibm-modules", "terraform-ibm-vpc", "v5.1.0", recursive=True
        )

    @pytest.mark.asyncio
    async def test_list_content_module_not_found(self, mock_config, mock_github_client):
        """Test error handling when module repository is not found."""
        # Setup
        request = ListContentRequest(module_id="nonexistent/module/ibm")

        mock_github_client.get_repository_info.side_effect = ModuleNotFoundError(
            "nonexistent/terraform-ibm-module",
            details={"reason": "Repository not found"},
        )

        # Execute & Verify
        with patch("tim_mcp.tools.list_content.GitHubClient") as MockGitHubClient:
            MockGitHubClient.return_value = mock_github_client
            mock_github_client.client = AsyncMock()
            mock_github_client.client.aclose = AsyncMock()

            with pytest.raises(ModuleNotFoundError) as exc_info:
                await list_content_impl(request, mock_config)

            assert "nonexistent/terraform-ibm-module" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_list_content_github_api_error(self, mock_config, mock_github_client):
        """Test that Registry API is used even when GitHub API fails (for solutions)."""
        # Setup
        request = ListContentRequest(module_id="terraform-ibm-modules/vpc/ibm")

        # GitHub fails for solutions lookup, but Registry succeeds
        mock_github_client.resolve_version.side_effect = GitHubError(
            "HTTP error getting repository info: 500 Server Error",
            status_code=500,
            response_body="Internal Server Error",
        )

        # Execute
        with patch("tim_mcp.tools.list_content.GitHubClient") as MockGitHubClient:
            with patch("tim_mcp.tools.list_content.TerraformClient") as MockTerraformClient:
                MockGitHubClient.return_value = mock_github_client
                mock_github_client.client = AsyncMock()
                mock_github_client.client.aclose = AsyncMock()

                # Mock TerraformClient to succeed
                mock_terraform_client = AsyncMock()
                MockTerraformClient.return_value = mock_terraform_client
                mock_terraform_client.client = AsyncMock()
                mock_terraform_client.client.aclose = AsyncMock()

                # Return empty structure from Registry (module with no examples/submodules)
                mock_terraform_client.get_module_structure.return_value = {
                    "version": "1.0.0",
                    "root": {"readme": "# Test Module\n\nTest description."},
                    "examples": [],
                    "submodules": [],
                }

                # Should succeed with Registry data even though GitHub failed
                result = await list_content_impl(request, mock_config)

                # Verify we got content from Registry API
                assert "# terraform-ibm-modules/vpc/ibm - Available Content" in result
                assert "**Version:** 1.0.0" in result
                assert "## Root Module" in result

    @pytest.mark.asyncio
    async def test_list_content_rate_limit_error(self, mock_config, mock_github_client):
        """Test error handling for Registry API rate limit errors."""
        # Setup
        request = ListContentRequest(module_id="terraform-ibm-modules/vpc/ibm")

        # Execute & Verify
        with patch("tim_mcp.tools.list_content.GitHubClient") as MockGitHubClient:
            with patch("tim_mcp.tools.list_content.TerraformClient") as MockTerraformClient:
                MockGitHubClient.return_value = mock_github_client
                mock_github_client.client = AsyncMock()
                mock_github_client.client.aclose = AsyncMock()

                # Mock TerraformClient to raise rate limit error
                mock_terraform_client = AsyncMock()
                MockTerraformClient.return_value = mock_terraform_client
                mock_terraform_client.client = AsyncMock()
                mock_terraform_client.client.aclose = AsyncMock()

                from tim_mcp.exceptions import TerraformRegistryError

                mock_terraform_client.get_module_structure.side_effect = TerraformRegistryError(
                    "HTTP error getting module structure: 429 Too Many Requests",
                    status_code=429,
                    response_body="Too Many Requests",
                )

                # Mock GitHub fallback to also fail with rate limit
                mock_github_client.get_repository_info.side_effect = RateLimitError(
                    "GitHub rate limit exceeded", reset_time=1234567890, api_name="GitHub"
                )

                with pytest.raises(RateLimitError) as exc_info:
                    await list_content_impl(request, mock_config)

                assert "GitHub rate limit exceeded" in str(exc_info.value)
                assert exc_info.value.reset_time == 1234567890

    @pytest.mark.asyncio
    async def test_list_content_invalid_module_id(self, mock_config):
        """Test error handling for invalid module ID format."""
        # Setup
        request = ListContentRequest(module_id="invalid-module-id")

        # Execute & Verify
        with pytest.raises(ValidationError) as exc_info:
            await list_content_impl(request, mock_config)

        assert "Invalid module_id format" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_list_content_empty_repository(
        self, mock_config, mock_github_client, sample_repo_info
    ):
        """Test content listing for empty repository."""
        # Setup
        request = ListContentRequest(module_id="terraform-ibm-modules/empty/ibm")

        mock_github_client.get_repository_info.return_value = sample_repo_info
        mock_github_client.resolve_version.return_value = "main"
        mock_github_client.get_repository_tree.return_value = []

        # Execute
        with patch("tim_mcp.tools.list_content.GitHubClient") as MockGitHubClient:
            MockGitHubClient.return_value = mock_github_client
            mock_github_client.client = AsyncMock()
            mock_github_client.client.aclose = AsyncMock()
            result = await list_content_impl(request, mock_config)

        # Verify
        assert "# terraform-ibm-modules/empty/ibm - Available Content" in result
        assert "**Version:** main" in result
        # Should only have root module section with no description since no README
        assert "## Root Module" in result
        assert "**Path:** `` (empty string)" in result
        # Should not have other sections since no content
        assert "## Examples" not in result
        assert "## Submodules" not in result

    @pytest.mark.asyncio
    async def test_list_content_readme_parsing_fallback(
        self, mock_config, mock_github_client, sample_tree_response, sample_repo_info
    ):
        """Test fallback to generic descriptions when Registry has no READMEs."""
        # Setup
        request = ListContentRequest(module_id="terraform-ibm-modules/vpc/ibm")

        mock_github_client.resolve_version.return_value = "main"
        mock_github_client.get_repository_tree.return_value = sample_tree_response

        # Mock get_file_content to fail for README files
        async def mock_get_file_content(owner, repo, path, ref="HEAD"):
            raise ModuleNotFoundError(f"{owner}/{repo}/{path}")

        mock_github_client.get_file_content.side_effect = mock_get_file_content

        # Execute
        with patch("tim_mcp.tools.list_content.GitHubClient") as MockGitHubClient:
            with patch("tim_mcp.tools.list_content.TerraformClient") as MockTerraformClient:
                MockGitHubClient.return_value = mock_github_client
                mock_github_client.client = AsyncMock()
                mock_github_client.client.aclose = AsyncMock()

                # Mock TerraformClient with empty READMEs
                mock_terraform_client = AsyncMock()
                MockTerraformClient.return_value = mock_terraform_client
                mock_terraform_client.client = AsyncMock()
                mock_terraform_client.client.aclose = AsyncMock()

                # Return structure with no READMEs
                mock_terraform_client.get_module_structure.return_value = {
                    "version": "main",
                    "root": {},  # No readme
                    "examples": [
                        {"path": "examples/basic"},  # No readme
                    ],
                    "submodules": [
                        {"path": "modules/landing-zone-vpc"},  # No readme
                    ],
                }

                result = await list_content_impl(request, mock_config)

        # Verify
        assert "# terraform-ibm-modules/vpc/ibm - Available Content" in result

        # Should still have sections but with generic descriptions
        assert "## Root Module" in result
        assert "**Path:** `` (empty string)" in result
        assert "Root module containing the main Terraform configuration" in result

        assert "## Examples" in result
        assert "**Path:** `examples/basic`" in result
        # Generic description for examples
        assert "Example configuration" in result

        assert "## Submodules" in result
        assert "**Path:** `modules/landing-zone-vpc`" in result
        # Generic description for submodules
        assert "Submodule providing" in result

    @pytest.mark.asyncio
    async def test_list_content_path_categorization(
        self, mock_config, mock_github_client, sample_repo_info
    ):
        """Test correct categorization of different path types."""
        # Setup with diverse path structure
        diverse_tree = [
            {"path": "README.md", "type": "blob", "mode": "100644"},
            {"path": "main.tf", "type": "blob", "mode": "100644"},
            {"path": "examples/basic", "type": "tree", "mode": "040000"},
            {"path": "examples/advanced", "type": "tree", "mode": "040000"},
            {"path": "examples/fscloud", "type": "tree", "mode": "040000"},
            {"path": "modules/dns", "type": "tree", "mode": "040000"},
            {"path": "modules/security", "type": "tree", "mode": "040000"},
            {"path": "docs", "type": "tree", "mode": "040000"},
            {"path": "test", "type": "tree", "mode": "040000"},
            {"path": ".github", "type": "tree", "mode": "040000"},
        ]

        request = ListContentRequest(module_id="terraform-ibm-modules/test/ibm")

        mock_github_client.get_repository_info.return_value = sample_repo_info
        mock_github_client.get_repository_tree.return_value = diverse_tree

        async def mock_get_file_content(owner, repo, path, ref="HEAD"):
            raise ModuleNotFoundError(f"{owner}/{repo}/{path}")

        mock_github_client.get_file_content.side_effect = mock_get_file_content

        # Execute
        with patch("tim_mcp.tools.list_content.GitHubClient") as MockGitHubClient:
            MockGitHubClient.return_value = mock_github_client
            mock_github_client.client = AsyncMock()
            mock_github_client.client.aclose = AsyncMock()
            result = await list_content_impl(request, mock_config)

        # Verify proper categorization
        assert "## Root Module" in result

        assert "## Examples" in result
        assert "`examples/basic`" in result
        assert "`examples/advanced`" in result
        assert "`examples/fscloud`" in result

        assert "## Submodules" in result
        assert "`modules/dns`" in result
        assert "`modules/security`" in result

        # Should not categorize non-relevant directories
        assert "`docs`" not in result
        assert "`test`" not in result
        assert "`.github`" not in result

    def test_extract_readme_summary(self):
        """Test README summary extraction logic."""
        from tim_mcp.tools.list_content import _extract_readme_summary

        # Test with standard README
        readme_content = """# VPC Module

This is a comprehensive module for creating IBM Cloud VPC resources.

## Features
- Creates VPC with subnets
- Configures security groups
- Sets up routing tables

## Usage
module "vpc" {
  source = "./vpc"
}
"""
        summary = _extract_readme_summary(readme_content)
        assert "comprehensive module for creating IBM Cloud VPC resources" in summary

        # Test with minimal README
        minimal_content = "# Basic Example\n\nSimple configuration."
        summary = _extract_readme_summary(minimal_content)
        assert "Simple configuration" in summary

        # Test with no description
        no_desc_content = "# Title Only"
        summary = _extract_readme_summary(no_desc_content)
        assert summary == "No description available."

        # Test with empty content
        empty_summary = _extract_readme_summary("")
        assert empty_summary == "No description available."

        # Test with code blocks
        code_block_content = """# Module

This module **creates** VPC resources.

```hcl
module "vpc" {
  source = "./vpc"
}
```

More details here.
"""
        summary = _extract_readme_summary(code_block_content)
        assert "creates VPC resources" in summary
        assert "```" not in summary

        # Test with markdown formatting
        markdown_content = """# Test

This is **bold** and *italic* text with `code` and [link](http://example.com).
"""
        summary = _extract_readme_summary(markdown_content)
        assert "bold" in summary
        assert "italic" in summary
        assert "**" not in summary
        assert "*" not in summary
        assert "`" not in summary
        assert "[" not in summary

    def test_categorize_path(self):
        """Test path categorization logic."""
        from tim_mcp.tools.list_content import _categorize_path

        # Test examples
        assert _categorize_path("examples/basic") == "examples"
        assert _categorize_path("examples/advanced/nested") == "examples"
        assert _categorize_path("Examples/Basic") == "examples"  # Case insensitive

        # Test alternative example naming
        assert _categorize_path("sample/basic") == "examples"
        assert _categorize_path("samples/advanced") == "examples"

        # Test submodules
        assert _categorize_path("modules/dns") == "submodules"
        assert _categorize_path("modules/security/advanced") == "submodules"
        assert _categorize_path("Modules/vpc") == "submodules"  # Case insensitive

        # Test that solutions/patterns are now skipped (return None)
        assert _categorize_path("patterns/enterprise") is None
        assert _categorize_path("solutions/complete") is None
        assert _categorize_path("Patterns/VPC") is None  # Case insensitive

        # Test non-categorized paths (should return None)
        assert _categorize_path("docs") is None
        assert _categorize_path("test") is None
        assert _categorize_path("tests") is None
        assert _categorize_path(".github") is None
        assert _categorize_path("terraform") is None
        assert _categorize_path(".terraform") is None
        assert _categorize_path("node_modules") is None
        assert _categorize_path("__pycache__") is None
        assert _categorize_path("coverage") is None

        # Test file-like paths (should return None)
        assert _categorize_path("main.tf") is None
        assert _categorize_path("README.md") is None

    def test_extract_repo_from_module_id(self):
        """Test repository extraction from module ID."""
        from tim_mcp.tools.list_content import _extract_repo_from_module_id

        # Test terraform-ibm-modules namespace
        owner, repo = _extract_repo_from_module_id("terraform-ibm-modules/vpc/ibm")
        assert owner == "terraform-ibm-modules"
        assert repo == "terraform-ibm-vpc"

        # Test other namespace
        owner, repo = _extract_repo_from_module_id("hashicorp/consul/aws")
        assert owner == "hashicorp"
        assert repo == "terraform-consul-aws"

        # Test invalid format
        with pytest.raises(ModuleNotFoundError):
            _extract_repo_from_module_id("invalid-format")

    def test_clean_markdown(self):
        """Test markdown cleaning functionality."""
        from tim_mcp.tools.list_content import _clean_markdown

        # Test basic formatting removal
        text = "This is **bold** and *italic* text with `code`."
        cleaned = _clean_markdown(text)
        assert cleaned == "This is bold and italic text with code."

        # Test link removal
        text = "Check out [this link](https://example.com) for more info."
        cleaned = _clean_markdown(text)
        assert cleaned == "Check out this link for more info."

        # Test image removal
        text = "Here's an image: ![alt text](image.png) and more text."
        cleaned = _clean_markdown(text)
        assert cleaned == "Here's an image: and more text."

        # Test blockquotes
        text = "> This is a blockquote\n> with multiple lines"
        cleaned = _clean_markdown(text)
        assert cleaned == "This is a blockquote with multiple lines"

        # Test multiple spaces
        text = "This   has    many     spaces."
        cleaned = _clean_markdown(text)
        assert cleaned == "This has many spaces."

        # Test complex markdown
        text = "**Bold** *italic* `code` [link](url) ![img](pic.png) > quote"
        cleaned = _clean_markdown(text)
        assert cleaned == "Bold italic code link quote"


# Made with TDD
