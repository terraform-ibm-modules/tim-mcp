"""
Tests for the get_module_details tool implementation.

Following TDD methodology - these tests are written first to define the expected behavior.
"""

from unittest.mock import AsyncMock, patch

import pytest

from tim_mcp.config import Config
from tim_mcp.exceptions import (
    ModuleNotFoundError,
    RateLimitError,
    TerraformRegistryError,
    ValidationError,
)
from tim_mcp.types import ModuleDetailsRequest


@pytest.fixture
def config():
    """Create a test configuration."""
    return Config()


@pytest.fixture
def sample_module_details_response():
    """Sample API response for module details."""
    return {
        "id": "terraform-ibm-modules/vpc/ibm",
        "namespace": "terraform-ibm-modules",
        "name": "vpc",
        "provider": "ibm",
        "version": "7.4.2",
        "description": (
            "Provisions and configures IBM Cloud VPC resources including subnets, security groups, "
            "routing tables, and load balancers."
        ),
        "source": "https://github.com/terraform-ibm-modules/terraform-ibm-vpc",
        "downloads": 53004,
        "verified": True,
        "published_at": "2025-09-02T10:30:00.000Z",
        "root": {
            "inputs": [
                {
                    "name": "vpc_name",
                    "type": "string",
                    "description": "Name of the VPC instance",
                    "required": True,
                },
                {
                    "name": "resource_group_id",
                    "type": "string",
                    "description": "ID of the resource group",
                    "required": True,
                },
                {
                    "name": "locations",
                    "type": "list(string)",
                    "description": "List of zones for VPC deployment",
                    "default": ["us-south-1"],
                    "required": False,
                },
                {
                    "name": "vpc_tags",
                    "type": "list(string)",
                    "description": "List of tags to apply",
                    "default": [],
                    "required": False,
                },
            ],
            "outputs": [
                {
                    "name": "vpc_id",
                    "type": "string",
                    "description": "ID of the created VPC",
                },
                {
                    "name": "vpc_crn",
                    "type": "string",
                    "description": "CRN of the VPC instance",
                },
            ],
            "dependencies": [{"name": "ibm", "version": ">= 1.49.0"}],
        },
        "versions": ["7.4.2", "7.4.1", "7.4.0", "7.3.1"],
    }


@pytest.fixture
def expected_markdown_output():
    """Expected markdown output for the sample module."""
    return """# terraform-ibm-modules/vpc/ibm - Module Details

**Latest Version:** v7.4.2
**Published:** 2025-09-02
**Downloads:** 53,004
**Source:** https://github.com/terraform-ibm-modules/terraform-ibm-vpc

## Description
Provisions and configures IBM Cloud VPC resources including subnets, security groups, routing tables, and load balancers.

## Required Inputs
- **vpc_name** (string): Name of the VPC instance
- **resource_group_id** (string): ID of the resource group

## Optional Inputs
- **locations** (list(string)): List of zones for VPC deployment (default: ['us-south-1'])
- **vpc_tags** (list(string)): List of tags to apply (default: [])

## Outputs
- **vpc_id** (string): ID of the created VPC
- **vpc_crn** (string): CRN of the VPC instance

## Dependencies
**Provider Requirements:**
- IBM Cloud Provider >= 1.49.0

**Module Dependencies:** None

## Available Versions
v7.4.2, v7.4.1, v7.4.0, v7.3.1"""


class TestGetModuleDetailsValidation:
    """Test input validation for get_module_details."""

    def test_valid_module_id_parsing(self):
        """Test that valid module IDs are parsed correctly."""
        # This will be implemented when we create the actual function
        from tim_mcp.utils.module_id import parse_module_id

        # Test standard format
        namespace, name, provider = parse_module_id("terraform-ibm-modules/vpc/ibm")
        assert namespace == "terraform-ibm-modules"
        assert name == "vpc"
        assert provider == "ibm"

        # Test with version included
        from tim_mcp.utils.module_id import parse_module_id_with_version

        namespace, name, provider, version = parse_module_id_with_version(
            "terraform-ibm-modules/vpc/ibm/1.2.3"
        )
        assert namespace == "terraform-ibm-modules"
        assert name == "vpc"
        assert provider == "ibm"
        assert version == "1.2.3"

    def test_invalid_module_id_format(self):
        """Test validation fails for invalid module ID format."""
        from tim_mcp.utils.module_id import parse_module_id

        with pytest.raises(ValidationError) as exc_info:
            parse_module_id("invalid-format")

        assert "Invalid module_id format" in str(exc_info.value)
        assert exc_info.value.field == "module_id"

    def test_empty_module_id_components(self):
        """Test validation fails for empty components."""
        from tim_mcp.utils.module_id import parse_module_id

        with pytest.raises(ValidationError) as exc_info:
            parse_module_id("//")

        assert exc_info.value.field == "module_id"

    def test_module_id_with_extra_slashes(self):
        """Test validation fails for module ID with too many slashes."""
        from tim_mcp.utils.module_id import parse_module_id

        with pytest.raises(ValidationError):
            parse_module_id("namespace/name/provider/version/extra")


class TestGetModuleDetailsSuccess:
    """Test successful module details retrieval."""

    @pytest.mark.asyncio
    async def test_get_module_details_latest_version(
        self, config, sample_module_details_response, expected_markdown_output
    ):
        """Test getting module details for latest version."""
        from tim_mcp.tools.details import get_module_details_impl

        # Mock the TerraformClient
        with patch("tim_mcp.tools.details.TerraformClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.get_module_details.return_value = sample_module_details_response
            mock_client.get_module_versions.return_value = [
                "7.4.2",
                "7.4.1",
                "7.4.0",
                "7.3.1",
            ]

            request = ModuleDetailsRequest(
                module_id="terraform-ibm-modules/vpc/ibm", version="latest"
            )

            result = await get_module_details_impl(request, config)

            assert result == expected_markdown_output
            mock_client.get_module_details.assert_called_once_with(
                namespace="terraform-ibm-modules",
                name="vpc",
                provider="ibm",
                version="latest",
            )

    @pytest.mark.asyncio
    async def test_get_module_details_specific_version(
        self, config, sample_module_details_response
    ):
        """Test getting module details for specific version."""
        from tim_mcp.tools.details import get_module_details_impl

        # Modify response for specific version
        specific_version_response = sample_module_details_response.copy()
        specific_version_response["version"] = "7.4.1"

        with patch("tim_mcp.tools.details.TerraformClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.get_module_details.return_value = specific_version_response
            mock_client.get_module_versions.return_value = [
                "7.4.2",
                "7.4.1",
                "7.4.0",
                "7.3.1",
            ]

            request = ModuleDetailsRequest(
                module_id="terraform-ibm-modules/vpc/ibm/7.4.1"
            )

            result = await get_module_details_impl(request, config)

            assert "**Latest Version:** v7.4.1" in result
            mock_client.get_module_details.assert_called_once_with(
                namespace="terraform-ibm-modules",
                name="vpc",
                provider="ibm",
                version="7.4.1",
            )

    @pytest.mark.asyncio
    async def test_module_with_no_dependencies(self, config):
        """Test module with no dependencies."""
        from tim_mcp.tools.details import get_module_details_impl

        response_no_deps = {
            "id": "simple/module/aws",
            "namespace": "simple",
            "name": "module",
            "provider": "aws",
            "version": "1.0.0",
            "description": "A simple module",
            "source": "https://github.com/simple/terraform-module",
            "downloads": 100,
            "verified": False,
            "published_at": "2025-01-01T00:00:00.000Z",
            "root": {"inputs": [], "outputs": [], "dependencies": []},
            "versions": ["1.0.0"],
        }

        with patch("tim_mcp.tools.details.TerraformClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.get_module_details.return_value = response_no_deps
            mock_client.get_module_versions.return_value = ["1.0.0"]

            request = ModuleDetailsRequest(module_id="simple/module/aws")

            result = await get_module_details_impl(request, config)

            assert "**Module Dependencies:** None" in result
            assert "**Provider Requirements:**\nNone" in result

    @pytest.mark.asyncio
    async def test_module_with_module_dependencies(self, config):
        """Test module with both provider and module dependencies."""
        from tim_mcp.tools.details import get_module_details_impl

        response_with_deps = {
            "id": "complex/module/aws",
            "namespace": "complex",
            "name": "module",
            "provider": "aws",
            "version": "2.0.0",
            "description": "A complex module",
            "source": "https://github.com/complex/terraform-module",
            "downloads": 500,
            "verified": True,
            "published_at": "2025-01-15T12:00:00.000Z",
            "root": {
                "inputs": [],
                "outputs": [],
                "dependencies": [
                    {"name": "aws", "version": ">= 4.0.0"},
                    {"name": "terraform-aws-modules/vpc/aws", "version": "~> 3.0"},
                ],
            },
            "versions": ["2.0.0"],
        }

        with patch("tim_mcp.tools.details.TerraformClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.get_module_details.return_value = response_with_deps
            mock_client.get_module_versions.return_value = ["2.0.0"]

            request = ModuleDetailsRequest(module_id="complex/module/aws")

            result = await get_module_details_impl(request, config)

            assert "**Provider Requirements:**" in result
            assert "- AWS Provider >= 4.0.0" in result
            assert "**Module Dependencies:**" in result
            assert "- terraform-aws-modules/vpc/aws ~> 3.0" in result


class TestGetModuleDetailsErrors:
    """Test error handling for get_module_details."""

    @pytest.mark.asyncio
    async def test_module_not_found(self, config):
        """Test handling when module is not found."""
        from tim_mcp.tools.details import get_module_details_impl

        with patch("tim_mcp.tools.details.TerraformClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.get_module_details.side_effect = TerraformRegistryError(
                "Module not found", status_code=404
            )

            request = ModuleDetailsRequest(module_id="nonexistent/module/aws")

            with pytest.raises(ModuleNotFoundError) as exc_info:
                await get_module_details_impl(request, config)

            assert "nonexistent/module/aws" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_rate_limit_error(self, config):
        """Test handling of rate limit errors."""
        from tim_mcp.tools.details import get_module_details_impl

        with patch("tim_mcp.tools.details.TerraformClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.get_module_details.side_effect = RateLimitError(
                "Rate limit exceeded", reset_time=1640995200
            )

            request = ModuleDetailsRequest(module_id="test/module/aws")

            with pytest.raises(RateLimitError):
                await get_module_details_impl(request, config)

    @pytest.mark.asyncio
    async def test_api_error_handling(self, config):
        """Test handling of general API errors."""
        from tim_mcp.tools.details import get_module_details_impl

        with patch("tim_mcp.tools.details.TerraformClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.get_module_details.side_effect = TerraformRegistryError(
                "Internal server error", status_code=500
            )

            request = ModuleDetailsRequest(module_id="test/module/aws")

            with pytest.raises(TerraformRegistryError) as exc_info:
                await get_module_details_impl(request, config)

            assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_invalid_module_id_format_in_request(self, config):
        """Test handling of invalid module ID in request."""
        from tim_mcp.tools.details import get_module_details_impl

        request = ModuleDetailsRequest(module_id="invalid-format")

        with pytest.raises(TerraformRegistryError) as exc_info:
            await get_module_details_impl(request, config)

        assert "Invalid module_id format" in str(exc_info.value)


class TestMarkdownFormatting:
    """Test the markdown formatting functionality."""

    def test_format_module_details_basic(self):
        """Test basic markdown formatting."""
        from tim_mcp.tools.details import format_module_details

        module_data = {
            "id": "test/module/aws",
            "namespace": "test",
            "name": "module",
            "provider": "aws",
            "version": "1.0.0",
            "description": "Test module",
            "source": "https://github.com/test/module",
            "downloads": 1000,
            "published_at": "2025-01-01T12:00:00.000Z",
            "root": {"inputs": [], "outputs": [], "dependencies": []},
        }

        versions = ["1.0.0"]

        result = format_module_details(module_data, versions)

        assert "# test/module/aws - Module Details" in result
        assert "**Latest Version:** v1.0.0" in result
        assert "**Published:** 2025-01-01" in result
        assert "**Downloads:** 1,000" in result
        assert "**Source:** https://github.com/test/module" in result

    def test_format_inputs_and_outputs(self):
        """Test formatting of inputs and outputs."""
        from tim_mcp.tools.details import format_inputs, format_outputs

        inputs = [
            {
                "name": "vpc_name",
                "type": "string",
                "description": "Name of the VPC",
                "required": True,
            },
            {
                "name": "tags",
                "type": "map(string)",
                "description": "Resource tags",
                "default": {},
                "required": False,
            },
        ]

        outputs = [{"name": "vpc_id", "type": "string", "description": "ID of the VPC"}]

        required_result, optional_result = format_inputs(inputs)
        output_result = format_outputs(outputs)

        assert "- **vpc_name** (string): Name of the VPC" in required_result
        assert (
            "- **tags** (map(string)): Resource tags (default: {})" in optional_result
        )
        assert "- **vpc_id** (string): ID of the VPC" in output_result

    def test_format_dependencies(self):
        """Test formatting of dependencies."""
        from tim_mcp.tools.details import format_dependencies

        dependencies = [
            {"name": "aws", "version": ">= 4.0.0"},
            {"name": "terraform-aws-modules/vpc/aws", "version": "~> 3.0"},
        ]

        provider_deps, module_deps = format_dependencies(dependencies)

        assert "- AWS Provider >= 4.0.0" in provider_deps
        assert "- terraform-aws-modules/vpc/aws ~> 3.0" in module_deps

    def test_format_large_download_count(self):
        """Test formatting of large download counts with commas."""
        from tim_mcp.tools.details import format_download_count

        assert format_download_count(1000) == "1,000"
        assert format_download_count(1000000) == "1,000,000"
        assert format_download_count(53004) == "53,004"

    def test_format_published_date(self):
        """Test formatting of published date."""
        from tim_mcp.tools.details import format_published_date

        # Test ISO 8601 format
        result = format_published_date("2025-09-02T10:30:00.000Z")
        assert result == "2025-09-02"

        # Test alternative format
        result = format_published_date("2025-01-15T12:00:00Z")
        assert result == "2025-01-15"

    def test_format_version_list(self):
        """Test formatting of version list."""
        from tim_mcp.tools.details import format_version_list

        versions = ["7.4.2", "7.4.1", "7.4.0", "7.3.1"]
        result = format_version_list(versions)

        assert result == "v7.4.2, v7.4.1, v7.4.0, v7.3.1"
