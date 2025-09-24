"""
Tests for the get_content tool.

This module contains comprehensive tests for the get_content tool implementation,
following TDD methodology.
"""

import asyncio
import re
from unittest.mock import AsyncMock, Mock

import pytest

from tim_mcp.config import Config
from tim_mcp.exceptions import GitHubError, ModuleNotFoundError
from tim_mcp.tools.get_content import get_content_impl
from tim_mcp.types import GetContentRequest


class TestGetContentTool:
    """Test cases for the get_content tool."""

    @pytest.fixture
    def config(self):
        """Test configuration."""
        return Config()

    @pytest.fixture
    def mock_github_client(self):
        """Mock GitHub client."""
        client = AsyncMock()
        # Make synchronous methods actually synchronous
        client._extract_repo_from_module_id = Mock()
        client.match_file_patterns = Mock()
        return client

    @pytest.fixture
    def sample_readme_content(self):
        """Sample README content for testing."""
        return {
            "name": "README.md",
            "path": "README.md",
            "content": (
                "IyBTYW1wbGUgTW9kdWxlCgpBIHNhbXBsZSBUZXJyYWZvcm0gbW9kdWxlIGZvciBJQk0gQ2xvdWQuCgojIyBFeGFtcGxlcwoKU2VlIGBleGFtcGxlcy9i"
                "YXNpY2AgZm9yIGEgc2ltcGxlIGV4YW1wbGUu"
            ),
            "encoding": "base64",
            "size": 100,
            "decoded_content": (
                "# Sample Module\n\nA sample Terraform module for IBM Cloud.\n\n"
                "## Examples\n\nSee `examples/basic` for a simple example."
            ),
        }

    @pytest.fixture
    def sample_main_tf_content(self):
        """Sample main.tf content for testing."""
        return {
            "name": "main.tf",
            "path": "examples/basic/main.tf",
            "content": (
                "bW9kdWxlICJ2cGMiIHsKICBzb3VyY2UgPSAiLi4vLi4vIgogIHZwY19uYW1lID0gdmFyLnZwY19uYW1lCiAgcmVzb3VyY2VfZ3JvdXBfaWQgPSB2"
                "YXIucmVzb3VyY2VfZ3JvdXBfaWQKICBsb2NhdGlvbnMgPSBbInVzLXNvdXRoLTEiXQp9"
            ),
            "encoding": "base64",
            "size": 150,
            "decoded_content": (
                'module "vpc" {\n  source = "../../"\n  vpc_name = var.vpc_name\n  '
                'resource_group_id = var.resource_group_id\n  locations = ["us-south-1"]\n}'
            ),
        }

    @pytest.fixture
    def sample_variables_tf_content(self):
        """Sample variables.tf content for testing."""
        return {
            "name": "variables.tf",
            "path": "examples/basic/variables.tf",
            "content": (
                "dmFyaWFibGUgInZwY19uYW1lIiB7CiAgdHlwZSAgICAgICAgPSBzdHJpbmcKICBkZXNjcmlwdGlvbiA9ICJOYW1lIG9mIHRoZSBWUEMiCn0="
            ),
            "encoding": "base64",
            "size": 80,
            "decoded_content": 'variable "vpc_name" {\n  type        = string\n  description = "Name of the VPC"\n}',
        }

    @pytest.fixture
    def sample_directory_contents(self):
        """Sample directory contents for testing."""
        return [
            {
                "name": "main.tf",
                "path": "examples/basic/main.tf",
                "type": "file",
                "size": 150,
            },
            {
                "name": "variables.tf",
                "path": "examples/basic/variables.tf",
                "type": "file",
                "size": 80,
            },
            {
                "name": "outputs.tf",
                "path": "examples/basic/outputs.tf",
                "type": "file",
                "size": 60,
            },
            {
                "name": "test.tf",
                "path": "examples/basic/test.tf",
                "type": "file",
                "size": 40,
            },
        ]

    @pytest.mark.asyncio
    async def test_get_content_basic_example_with_all_files(
        self,
        config,
        mock_github_client,
        sample_readme_content,
        sample_main_tf_content,
        sample_variables_tf_content,
        sample_directory_contents,
    ):
        """Test getting content for basic example with all files."""
        request = GetContentRequest(
            module_id="terraform-ibm-modules/vpc/ibm",
            path="examples/basic",
            include_files=[".*"],
            include_readme=True,
            version="latest",
        )

        # Mock GitHub client methods
        mock_github_client._extract_repo_from_module_id.return_value = (
            "terraform-ibm-modules",
            "terraform-ibm-vpc",
        )
        mock_github_client.resolve_version.return_value = "latest"
        mock_github_client.get_directory_contents.return_value = (
            sample_directory_contents
        )
        mock_github_client.get_file_content.side_effect = [
            sample_readme_content,
            sample_main_tf_content,
            sample_variables_tf_content,
            {
                "name": "outputs.tf",
                "path": "examples/basic/outputs.tf",
                "content": "b3V0cHV0ICJ2cGNfaWQiIHsKICB2YWx1ZSA9IG1vZHVsZS52cGMudnBjX2lkCn0=",
                "encoding": "base64",
                "size": 60,
                "decoded_content": 'output "vpc_id" {\n  value = module.vpc.vpc_id\n}',
            },
            {
                "name": "test.tf",
                "path": "examples/basic/test.tf",
                "content": "IyBUZXN0IGZpbGU=",
                "encoding": "base64",
                "size": 40,
                "decoded_content": "# Test file",
            },
        ]
        mock_github_client.match_file_patterns.return_value = True

        result = await get_content_impl(request, config, mock_github_client)

        # Verify the result format
        assert "# terraform-ibm-modules/vpc/ibm - examples/basic" in result
        assert "**Version:** latest" in result
        assert "## README" in result
        assert "A sample Terraform module for IBM Cloud" in result
        assert "## Terraform Files" in result
        assert "### main.tf" in result
        assert "### variables.tf" in result
        assert "### outputs.tf" in result
        assert "### test.tf" in result
        assert 'module "vpc"' in result
        assert 'variable "vpc_name"' in result
        assert 'output "vpc_id"' in result

        # Verify GitHub client calls
        mock_github_client._extract_repo_from_module_id.assert_called_once_with(
            "terraform-ibm-modules/vpc/ibm"
        )
        mock_github_client.get_directory_contents.assert_called_once_with(
            "terraform-ibm-modules", "terraform-ibm-vpc", "examples/basic", "latest"
        )
        assert mock_github_client.get_file_content.call_count == 5  # README + 4 files

    @pytest.mark.asyncio
    async def test_get_content_with_terraform_files_only(
        self,
        config,
        mock_github_client,
        sample_readme_content,
        sample_main_tf_content,
        sample_variables_tf_content,
        sample_directory_contents,
    ):
        """Test getting content with Terraform files only."""
        request = GetContentRequest(
            module_id="terraform-ibm-modules/vpc/ibm",
            path="examples/basic",
            include_files=[".*\\.tf$"],
            exclude_files=[".*test.*"],
            include_readme=True,
            version="v5.1.0",
        )

        # Mock GitHub client methods
        mock_github_client._extract_repo_from_module_id.return_value = (
            "terraform-ibm-modules",
            "terraform-ibm-vpc",
        )
        mock_github_client.get_directory_contents.return_value = (
            sample_directory_contents
        )

        # Mock pattern matching to exclude test files
        def mock_match_patterns(
            file_path, include_patterns=None, exclude_patterns=None
        ):
            if exclude_patterns and any(
                re.search(pattern, file_path) for pattern in exclude_patterns
            ):
                return False
            if include_patterns:
                return any(
                    re.search(pattern, file_path) for pattern in include_patterns
                )
            return True

        mock_github_client.match_file_patterns.side_effect = mock_match_patterns
        mock_github_client.get_file_content.side_effect = [
            sample_readme_content,
            sample_main_tf_content,
            sample_variables_tf_content,
            {
                "name": "outputs.tf",
                "path": "examples/basic/outputs.tf",
                "content": "b3V0cHV0ICJ2cGNfaWQiIHsKICB2YWx1ZSA9IG1vZHVsZS52cGMudnBjX2lkCn0=",
                "encoding": "base64",
                "size": 60,
                "decoded_content": 'output "vpc_id" {\n  value = module.vpc.vpc_id\n}',
            },
        ]

        result = await get_content_impl(request, config, mock_github_client)

        # Verify test.tf is excluded
        assert "### test.tf" not in result
        assert "# Test file" not in result

        # Verify other tf files are included
        assert "### main.tf" in result
        assert "### variables.tf" in result
        assert "### outputs.tf" in result

    @pytest.mark.asyncio
    async def test_get_content_root_path(
        self, config, mock_github_client, sample_readme_content
    ):
        """Test getting content from root path."""
        request = GetContentRequest(
            module_id="terraform-ibm-modules/vpc/ibm",
            path="",
            include_files=["main.tf", "variables.tf", "outputs.tf"],
            include_readme=True,
            version="latest",
        )

        root_directory_contents = [
            {"name": "main.tf", "path": "main.tf", "type": "file", "size": 200},
            {
                "name": "variables.tf",
                "path": "variables.tf",
                "type": "file",
                "size": 150,
            },
            {"name": "outputs.tf", "path": "outputs.tf", "type": "file", "size": 100},
        ]

        # Mock GitHub client methods
        mock_github_client._extract_repo_from_module_id.return_value = (
            "terraform-ibm-modules",
            "terraform-ibm-vpc",
        )
        mock_github_client.get_directory_contents.return_value = root_directory_contents
        mock_github_client.match_file_patterns.return_value = True
        mock_github_client.get_file_content.side_effect = [
            sample_readme_content,
            {
                "name": "main.tf",
                "path": "main.tf",
                "content": "cmVzb3VyY2UgImlidl92cGMiICJ2cGMiIHsKICBuYW1lID0gdmFyLnZwY19uYW1lCn0=",
                "encoding": "base64",
                "size": 200,
                "decoded_content": 'resource "ibm_vpc" "vpc" {\n  name = var.vpc_name\n}',
            },
            {
                "name": "variables.tf",
                "path": "variables.tf",
                "content": "dmFyaWFibGUgInZwY19uYW1lIiB7CiAgdHlwZSA9IHN0cmluZwp9",
                "encoding": "base64",
                "size": 150,
                "decoded_content": 'variable "vpc_name" {\n  type = string\n}',
            },
            {
                "name": "outputs.tf",
                "path": "outputs.tf",
                "content": "b3V0cHV0ICJ2cGNfaWQiIHsKICB2YWx1ZSA9IGlidl92cGMudnBjLmlkCn0=",
                "encoding": "base64",
                "size": 100,
                "decoded_content": 'output "vpc_id" {\n  value = ibm_vpc.vpc.id\n}',
            },
        ]

        result = await get_content_impl(request, config, mock_github_client)

        # Verify root path in title
        assert "# terraform-ibm-modules/vpc/ibm" in result
        assert "- examples/basic" not in result  # Should not have path suffix for root
        assert "## Terraform Files" in result
        assert 'resource "ibm_vpc"' in result

    @pytest.mark.asyncio
    async def test_get_content_without_readme(
        self,
        config,
        mock_github_client,
        sample_main_tf_content,
        sample_directory_contents,
    ):
        """Test getting content without README."""
        request = GetContentRequest(
            module_id="terraform-ibm-modules/vpc/ibm",
            path="examples/basic",
            include_files=["main.tf"],
            include_readme=False,
            version="latest",
        )

        # Mock GitHub client methods
        mock_github_client._extract_repo_from_module_id.return_value = (
            "terraform-ibm-modules",
            "terraform-ibm-vpc",
        )
        mock_github_client.get_directory_contents.return_value = (
            sample_directory_contents
        )
        mock_github_client.match_file_patterns.return_value = True
        mock_github_client.get_file_content.return_value = sample_main_tf_content

        result = await get_content_impl(request, config, mock_github_client)

        # Verify README is not included
        assert "## README" not in result
        assert "A sample Terraform module" not in result

        # Verify only main.tf is included
        assert "### main.tf" in result
        assert 'module "vpc"' in result

        # Verify README.md was not fetched
        calls = mock_github_client.get_file_content.call_args_list
        readme_calls = [call for call in calls if "README.md" in str(call)]
        assert len(readme_calls) == 0

    @pytest.mark.asyncio
    async def test_get_content_empty_directory(self, config, mock_github_client):
        """Test getting content from empty directory."""
        request = GetContentRequest(
            module_id="terraform-ibm-modules/vpc/ibm",
            path="examples/empty",
            include_files=[".*"],
            include_readme=True,
            version="latest",
        )

        # Mock GitHub client methods
        mock_github_client._extract_repo_from_module_id.return_value = (
            "terraform-ibm-modules",
            "terraform-ibm-vpc",
        )
        mock_github_client.resolve_version.return_value = "latest"
        mock_github_client.get_directory_contents.return_value = []
        mock_github_client.get_file_content.side_effect = ModuleNotFoundError(
            "terraform-ibm-modules/terraform-ibm-vpc/README.md"
        )

        result = await get_content_impl(request, config, mock_github_client)

        # Verify basic structure exists even with no files
        assert "# terraform-ibm-modules/vpc/ibm - examples/empty" in result
        assert "**Version:** latest" in result
        assert "## Terraform Files" in result
        assert "No files found matching the specified criteria." in result

    @pytest.mark.asyncio
    async def test_get_content_module_not_found(self, config, mock_github_client):
        """Test handling module not found error."""
        request = GetContentRequest(
            module_id="nonexistent/module/provider",
            path="",
            include_files=[".*"],
            include_readme=True,
            version="latest",
        )

        # Mock GitHub client to raise ModuleNotFoundError
        mock_github_client._extract_repo_from_module_id.return_value = (
            "nonexistent",
            "terraform-nonexistent-module",
        )
        mock_github_client.get_directory_contents.side_effect = ModuleNotFoundError(
            "nonexistent/module/provider"
        )

        with pytest.raises(ModuleNotFoundError) as exc_info:
            await get_content_impl(request, config, mock_github_client)

            assert "nonexistent/module/provider" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_content_github_api_error(self, config, mock_github_client):
        """Test handling GitHub API error."""
        request = GetContentRequest(
            module_id="terraform-ibm-modules/vpc/ibm",
            path="examples/basic",
            include_files=[".*"],
            include_readme=True,
            version="latest",
        )

        # Mock GitHub client to raise GitHubError
        mock_github_client._extract_repo_from_module_id.return_value = (
            "terraform-ibm-modules",
            "terraform-ibm-vpc",
        )
        mock_github_client.get_directory_contents.side_effect = GitHubError(
            "API rate limit exceeded", status_code=429
        )

        with pytest.raises(GitHubError) as exc_info:
            await get_content_impl(request, config, mock_github_client)

            assert "API rate limit exceeded" in str(exc_info.value)
            assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_get_content_concurrent_file_fetching(
        self,
        config,
        mock_github_client,
        sample_readme_content,
        sample_main_tf_content,
        sample_variables_tf_content,
    ):
        """Test that files are fetched concurrently for efficiency."""
        request = GetContentRequest(
            module_id="terraform-ibm-modules/vpc/ibm",
            path="examples/basic",
            include_files=[".*\\.tf$"],
            include_readme=True,
            version="latest",
        )

        # Create a list to track call order and timing
        call_times = []

        async def track_file_fetch(*args, **kwargs):
            call_times.append(asyncio.get_event_loop().time())
            # Simulate some async work
            await asyncio.sleep(0.01)

            # Return appropriate content based on path
            path = args[2] if len(args) > 2 else kwargs.get("path", "")
            if "README.md" in path:
                return sample_readme_content
            elif "main.tf" in path:
                return sample_main_tf_content
            elif "variables.tf" in path:
                return sample_variables_tf_content
            else:
                return {
                    "name": "outputs.tf",
                    "path": "examples/basic/outputs.tf",
                    "content": "b3V0cHV0",
                    "encoding": "base64",
                    "size": 60,
                    "decoded_content": 'output "vpc_id" { value = "" }',
                }

        directory_contents = [
            {
                "name": "main.tf",
                "path": "examples/basic/main.tf",
                "type": "file",
                "size": 150,
            },
            {
                "name": "variables.tf",
                "path": "examples/basic/variables.tf",
                "type": "file",
                "size": 80,
            },
            {
                "name": "outputs.tf",
                "path": "examples/basic/outputs.tf",
                "type": "file",
                "size": 60,
            },
        ]

        # Mock GitHub client methods
        mock_github_client._extract_repo_from_module_id.return_value = (
            "terraform-ibm-modules",
            "terraform-ibm-vpc",
        )
        mock_github_client.get_directory_contents.return_value = directory_contents
        mock_github_client.match_file_patterns.return_value = True
        mock_github_client.get_file_content.side_effect = track_file_fetch

        await get_content_impl(request, config, mock_github_client)

        # Verify all files were fetched
        assert (
            mock_github_client.get_file_content.call_count == 4
        )  # README + 3 tf files

        # Verify concurrent execution - all calls should start close together
        # (within a small time window if they're truly concurrent)
        if len(call_times) > 1:
            max_time_diff = max(call_times) - min(call_times)
            assert max_time_diff < 0.1  # All calls should start within 100ms

    @pytest.mark.asyncio
    async def test_get_content_regex_pattern_matching(
        self, config, mock_github_client, sample_readme_content
    ):
        """Test regex pattern matching for file inclusion/exclusion."""
        request = GetContentRequest(
            module_id="terraform-ibm-modules/vpc/ibm",
            path="examples/complex",
            include_files=[".*\\.tf$", ".*\\.yaml$"],
            exclude_files=[".*test.*", ".*\\.tftest$"],
            include_readme=True,
            version="latest",
        )

        complex_directory_contents = [
            {
                "name": "main.tf",
                "path": "examples/complex/main.tf",
                "type": "file",
                "size": 200,
            },
            {
                "name": "variables.tf",
                "path": "examples/complex/variables.tf",
                "type": "file",
                "size": 150,
            },
            {
                "name": "test_main.tf",
                "path": "examples/complex/test_main.tf",
                "type": "file",
                "size": 100,
            },
            {
                "name": "config.yaml",
                "path": "examples/complex/config.yaml",
                "type": "file",
                "size": 80,
            },
            {
                "name": "example.tftest",
                "path": "examples/complex/example.tftest",
                "type": "file",
                "size": 60,
            },
            {
                "name": "README.txt",
                "path": "examples/complex/README.txt",
                "type": "file",
                "size": 40,
            },
        ]

        # Mock realistic pattern matching
        def mock_pattern_matching(
            file_path, include_patterns=None, exclude_patterns=None
        ):
            # Check exclude patterns first
            if exclude_patterns:
                for pattern in exclude_patterns:
                    if re.search(pattern, file_path):
                        return False

            # Check include patterns
            if include_patterns:
                for pattern in include_patterns:
                    if re.search(pattern, file_path):
                        return True
                return False

            return True

        # Mock GitHub client methods
        mock_github_client._extract_repo_from_module_id.return_value = (
            "terraform-ibm-modules",
            "terraform-ibm-vpc",
        )
        mock_github_client.get_directory_contents.return_value = (
            complex_directory_contents
        )
        mock_github_client.match_file_patterns.side_effect = mock_pattern_matching
        mock_github_client.get_file_content.side_effect = [
            sample_readme_content,
            {
                "name": "main.tf",
                "path": "examples/complex/main.tf",
                "content": "bWFpbi50Zg==",
                "encoding": "base64",
                "size": 200,
                "decoded_content": "main.tf",
            },
            {
                "name": "variables.tf",
                "path": "examples/complex/variables.tf",
                "content": "dmFyaWFibGVzLnRm",
                "encoding": "base64",
                "size": 150,
                "decoded_content": "variables.tf",
            },
            {
                "name": "config.yaml",
                "path": "examples/complex/config.yaml",
                "content": "Y29uZmlnLnlhbWw=",
                "encoding": "base64",
                "size": 80,
                "decoded_content": "config.yaml",
            },
        ]

        result = await get_content_impl(request, config, mock_github_client)

        # Verify included files
        assert "### main.tf" in result
        assert "### variables.tf" in result
        assert "### config.yaml" in result

        # Verify excluded files
        assert "### test_main.tf" not in result
        assert "### example.tftest" not in result
        assert "### README.txt" not in result

    @pytest.mark.asyncio
    async def test_get_content_specific_version(
        self, config, mock_github_client, sample_readme_content, sample_main_tf_content
    ):
        """Test getting content for a specific version/tag."""
        request = GetContentRequest(
            module_id="terraform-ibm-modules/vpc/ibm",
            path="examples/basic",
            include_files=["main.tf"],
            include_readme=True,
            version="v5.1.0",
        )

        # Mock GitHub client methods
        mock_github_client._extract_repo_from_module_id.return_value = (
            "terraform-ibm-modules",
            "terraform-ibm-vpc",
        )
        mock_github_client.resolve_version.return_value = "v5.1.0"
        mock_github_client.get_directory_contents.return_value = [
            {
                "name": "main.tf",
                "path": "examples/basic/main.tf",
                "type": "file",
                "size": 150,
            }
        ]
        mock_github_client.match_file_patterns.return_value = True
        mock_github_client.get_file_content.side_effect = [
            sample_readme_content,
            sample_main_tf_content,
        ]

        result = await get_content_impl(request, config, mock_github_client)

        # Verify version is passed to GitHub API calls
        mock_github_client.get_directory_contents.assert_called_once_with(
            "terraform-ibm-modules", "terraform-ibm-vpc", "examples/basic", "v5.1.0"
        )

        # Verify version appears in output
        assert "**Version:** v5.1.0" in result

    @pytest.mark.asyncio
    async def test_get_content_configuration_summary(
        self, config, mock_github_client, sample_readme_content
    ):
        """Test that configuration summary is included when appropriate."""
        request = GetContentRequest(
            module_id="terraform-ibm-modules/vpc/ibm",
            path="examples/basic",
            include_files=[".*\\.tf$"],
            include_readme=True,
            version="latest",
        )

        terraform_files = [
            {
                "name": "main.tf",
                "path": "examples/basic/main.tf",
                "content": "bW9kdWxlICJ2cGMiIHsKICBzb3VyY2UgPSAiLi4vLi4vIgogIHZwY19uYW1lID0gdmFyLnZwY19uYW1lCn0=",
                "encoding": "base64",
                "size": 150,
                "decoded_content": 'module "vpc" {\n  source = "../../"\n  vpc_name = var.vpc_name\n}',
            },
            {
                "name": "variables.tf",
                "path": "examples/basic/variables.tf",
                "content": "dmFyaWFibGUgInZwY19uYW1lIiB7CiAgdHlwZSA9IHN0cmluZwp9",
                "encoding": "base64",
                "size": 80,
                "decoded_content": 'variable "vpc_name" {\n  type = string\n}',
            },
            {
                "name": "outputs.tf",
                "path": "examples/basic/outputs.tf",
                "content": "b3V0cHV0ICJ2cGNfaWQiIHsKICB2YWx1ZSA9IG1vZHVsZS52cGMuaWQKfQ==",
                "encoding": "base64",
                "size": 60,
                "decoded_content": 'output "vpc_id" {\n  value = module.vpc.id\n}',
            },
        ]

        # Mock GitHub client methods
        mock_github_client._extract_repo_from_module_id.return_value = (
            "terraform-ibm-modules",
            "terraform-ibm-vpc",
        )
        mock_github_client.get_directory_contents.return_value = [
            {
                "name": "main.tf",
                "path": "examples/basic/main.tf",
                "type": "file",
                "size": 150,
            },
            {
                "name": "variables.tf",
                "path": "examples/basic/variables.tf",
                "type": "file",
                "size": 80,
            },
            {
                "name": "outputs.tf",
                "path": "examples/basic/outputs.tf",
                "type": "file",
                "size": 60,
            },
        ]
        mock_github_client.match_file_patterns.return_value = True
        mock_github_client.get_file_content.side_effect = [
            sample_readme_content,
            *terraform_files,
        ]

        result = await get_content_impl(request, config, mock_github_client)

        # Verify configuration summary section exists
        assert "## Configuration Summary" in result
        assert "**Required Inputs:**" in result
        assert "**Outputs:**" in result

    @pytest.mark.asyncio
    async def test_get_content_latest_version_resolution(
        self, config, mock_github_client, sample_readme_content, sample_main_tf_content
    ):
        """Test that 'latest' version is resolved to actual release tag."""
        request = GetContentRequest(
            module_id="terraform-ibm-modules/vpc/ibm",
            path="examples/basic",
            include_files=["main.tf"],
            include_readme=True,
            version="latest",
        )

        # Mock GitHub client methods
        mock_github_client._extract_repo_from_module_id.return_value = (
            "terraform-ibm-modules",
            "terraform-ibm-vpc",
        )

        # Mock version resolution to return a specific tag
        mock_github_client.resolve_version.return_value = "v3.2.1"

        mock_github_client.get_directory_contents.return_value = [
            {
                "name": "main.tf",
                "path": "examples/basic/main.tf",
                "type": "file",
                "size": 150,
            }
        ]
        mock_github_client.match_file_patterns.return_value = True
        mock_github_client.get_file_content.side_effect = [
            sample_readme_content,
            sample_main_tf_content,
        ]

        result = await get_content_impl(request, config, mock_github_client)

        # Verify version resolution was called
        mock_github_client.resolve_version.assert_called_once_with(
            "terraform-ibm-modules", "terraform-ibm-vpc", "latest"
        )

        # Verify resolved version is used in API calls
        mock_github_client.get_directory_contents.assert_called_once_with(
            "terraform-ibm-modules", "terraform-ibm-vpc", "examples/basic", "v3.2.1"
        )

        # Verify resolved version appears in output
        assert "**Version:** v3.2.1" in result

    @pytest.mark.asyncio
    async def test_get_content_latest_fallback_to_head(
        self, config, mock_github_client, sample_readme_content, sample_main_tf_content
    ):
        """Test that 'latest' version falls back to HEAD when no releases exist."""
        request = GetContentRequest(
            module_id="terraform-ibm-modules/vpc/ibm",
            path="examples/basic",
            include_files=["main.tf"],
            include_readme=True,
            version="latest",
        )

        # Mock GitHub client methods
        mock_github_client._extract_repo_from_module_id.return_value = (
            "terraform-ibm-modules",
            "terraform-ibm-vpc",
        )

        # Mock version resolution to return HEAD (no releases)
        mock_github_client.resolve_version.return_value = "HEAD"

        mock_github_client.get_directory_contents.return_value = [
            {
                "name": "main.tf",
                "path": "examples/basic/main.tf",
                "type": "file",
                "size": 150,
            }
        ]
        mock_github_client.match_file_patterns.return_value = True
        mock_github_client.get_file_content.side_effect = [
            sample_readme_content,
            sample_main_tf_content,
        ]

        result = await get_content_impl(request, config, mock_github_client)

        # Verify version resolution was called
        mock_github_client.resolve_version.assert_called_once_with(
            "terraform-ibm-modules", "terraform-ibm-vpc", "latest"
        )

        # Verify resolved version is used in API calls
        mock_github_client.get_directory_contents.assert_called_once_with(
            "terraform-ibm-modules", "terraform-ibm-vpc", "examples/basic", "HEAD"
        )

        # Verify resolved version appears in output
        assert "**Version:** HEAD" in result

    @pytest.mark.asyncio
    async def test_get_content_invalid_regex_patterns(
        self, config, mock_github_client, sample_readme_content, sample_main_tf_content
    ):
        """Test that invalid regex patterns are handled gracefully."""
        request = GetContentRequest(
            module_id="terraform-ibm-modules/vpc/ibm",
            path="examples/basic",
            include_files=[
                "*",
                "*.tf",
                ".*\\.tf$",
            ],  # Mix of invalid and valid patterns
            exclude_files=["+", "?", ".*test.*"],  # Mix of invalid and valid patterns
            include_readme=True,
            version="latest",
        )

        # Mock GitHub client methods
        mock_github_client._extract_repo_from_module_id.return_value = (
            "terraform-ibm-modules",
            "terraform-ibm-vpc",
        )
        mock_github_client.resolve_version.return_value = "latest"

        mock_github_client.get_directory_contents.return_value = [
            {
                "name": "main.tf",
                "path": "examples/basic/main.tf",
                "type": "file",
                "size": 150,
            },
            {
                "name": "test.tf",
                "path": "examples/basic/test.tf",
                "type": "file",
                "size": 100,
            },
        ]

        # Use the real match_file_patterns method to test error handling
        from tim_mcp.clients.github_client import GitHubClient
        from tim_mcp.config import Config

        real_client = GitHubClient(Config())

        def mock_match_patterns(
            file_path, include_patterns=None, exclude_patterns=None
        ):
            return real_client.match_file_patterns(
                file_path, include_patterns, exclude_patterns
            )

        mock_github_client.match_file_patterns.side_effect = mock_match_patterns
        mock_github_client.get_file_content.side_effect = [
            sample_readme_content,
            sample_main_tf_content,
        ]

        # This should not raise an exception despite invalid patterns
        result = await get_content_impl(request, config, mock_github_client)

        # Verify the request completed successfully
        assert "**Version:** latest" in result
        assert "# terraform-ibm-modules/vpc/ibm - examples/basic" in result

    @pytest.mark.asyncio
    async def test_get_content_all_invalid_patterns(
        self, config, mock_github_client, sample_readme_content
    ):
        """Test handling when all regex patterns are invalid."""
        request = GetContentRequest(
            module_id="terraform-ibm-modules/vpc/ibm",
            path="examples/basic",
            include_files=["*", "+", "?"],  # All invalid patterns
            include_readme=True,
            version="latest",
        )

        # Mock GitHub client methods
        mock_github_client._extract_repo_from_module_id.return_value = (
            "terraform-ibm-modules",
            "terraform-ibm-vpc",
        )
        mock_github_client.resolve_version.return_value = "latest"

        mock_github_client.get_directory_contents.return_value = [
            {
                "name": "main.tf",
                "path": "examples/basic/main.tf",
                "type": "file",
                "size": 150,
            }
        ]

        # Use the real match_file_patterns method to test error handling
        from tim_mcp.clients.github_client import GitHubClient
        from tim_mcp.config import Config

        real_client = GitHubClient(Config())

        def mock_match_patterns(
            file_path, include_patterns=None, exclude_patterns=None
        ):
            return real_client.match_file_patterns(
                file_path, include_patterns, exclude_patterns
            )

        mock_github_client.match_file_patterns.side_effect = mock_match_patterns
        mock_github_client.get_file_content.side_effect = [sample_readme_content]

        # Should still work - when all include patterns are invalid, defaults to including all files
        result = await get_content_impl(request, config, mock_github_client)

        # Verify the request completed successfully with README
        assert "**Version:** latest" in result
        assert "# terraform-ibm-modules/vpc/ibm - examples/basic" in result
        assert "## README" in result

    @pytest.mark.asyncio
    async def test_get_content_glob_patterns_error_scenario(
        self, config, mock_github_client, sample_readme_content
    ):
        """Test the specific error scenario reported by user: glob patterns causing regex errors."""
        request = GetContentRequest(
            module_id="terraform-ibm-modules/vpc/ibm",
            path="examples/basic",
            include_files=[
                "*.tf"
            ],  # Common glob pattern that causes "nothing to repeat" error
            include_readme=True,
            version="latest",
        )

        # Mock GitHub client methods
        mock_github_client._extract_repo_from_module_id.return_value = (
            "terraform-ibm-modules",
            "terraform-ibm-vpc",
        )
        mock_github_client.resolve_version.return_value = "latest"

        mock_github_client.get_directory_contents.return_value = [
            {
                "name": "main.tf",
                "path": "examples/basic/main.tf",
                "type": "file",
                "size": 150,
            }
        ]

        # Use the real match_file_patterns method (this would previously fail)
        from tim_mcp.clients.github_client import GitHubClient
        from tim_mcp.config import Config

        real_client = GitHubClient(Config())

        def mock_match_patterns(
            file_path, include_patterns=None, exclude_patterns=None
        ):
            return real_client.match_file_patterns(
                file_path, include_patterns, exclude_patterns
            )

        mock_github_client.match_file_patterns.side_effect = mock_match_patterns
        mock_github_client.get_file_content.side_effect = [sample_readme_content]

        # This should now work without throwing "nothing to repeat at position 0" error
        result = await get_content_impl(request, config, mock_github_client)

        # Verify the request completed successfully
        assert "**Version:** latest" in result
        assert "# terraform-ibm-modules/vpc/ibm - examples/basic" in result
        # Should still include README even though pattern was invalid
        assert "## README" in result

    @pytest.mark.asyncio
    async def test_get_content_include_files_bug_reproduction(
        self, config, mock_github_client, sample_readme_content
    ):
        """Test that reproduces the specific bug in match_file_patterns logic with include_files."""
        request = GetContentRequest(
            module_id="terraform-ibm-modules/vpc/ibm",
            path="examples/basic",
            include_files=["main.tf"],  # First pattern matches immediately, causing bug
            include_readme=True,
            version="latest",
        )

        # Mock GitHub client methods
        mock_github_client._extract_repo_from_module_id.return_value = (
            "terraform-ibm-modules",
            "terraform-ibm-vpc",
        )
        mock_github_client.resolve_version.return_value = "latest"

        # Set up directory with both matching and non-matching files
        mock_github_client.get_directory_contents.return_value = [
            {
                "name": "main.tf",
                "path": "examples/basic/main.tf",
                "type": "file",
                "size": 150,
            },
            {
                "name": "variables.tf",
                "path": "examples/basic/variables.tf",
                "type": "file",
                "size": 80,
            },
        ]

        # Use the real match_file_patterns method to reproduce the bug
        from tim_mcp.clients.github_client import GitHubClient
        from tim_mcp.config import Config

        real_client = GitHubClient(Config())

        def mock_match_patterns(
            file_path, include_patterns=None, exclude_patterns=None
        ):
            return real_client.match_file_patterns(
                file_path, include_patterns, exclude_patterns
            )

        mock_github_client.match_file_patterns.side_effect = mock_match_patterns

        # Mock file content for main.tf
        mock_github_client.get_file_content.side_effect = [
            sample_readme_content,
            {
                "name": "main.tf",
                "path": "examples/basic/main.tf",
                "content": "bWFpbi50Zg==",
                "encoding": "base64",
                "size": 150,
                "decoded_content": "# main.tf content",
            },
        ]

        result = await get_content_impl(request, config, mock_github_client)

        # Verify that only main.tf is included (not variables.tf)
        assert "### main.tf" in result
        assert "### variables.tf" not in result

        # Verify the matching logic worked correctly
        # With the bug, this might fail if valid_include_matched logic is broken
        assert "# main.tf content" in result
