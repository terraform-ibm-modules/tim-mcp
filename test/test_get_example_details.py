"""
Tests for get_example_details tool.
"""

import pytest

from tim_mcp.config import Config
from tim_mcp.exceptions import ModuleNotFoundError, TerraformRegistryError
from tim_mcp.tools.get_example_details import (
    format_example_dependencies,
    format_example_details,
    format_example_inputs,
    format_example_outputs,
    format_example_resources,
    get_example_details_impl,
)
from tim_mcp.types import GetExampleDetailsRequest


@pytest.fixture
def sample_example_data():
    """Sample example data from Registry API."""
    return {
        "path": "examples/basic",
        "name": "basic",
        "readme": "# Basic example\n\nA basic example that creates a VPC.\n\nThis example demonstrates:\n- Creating a VPC\n- Setting up subnets\n- Configuring security groups",
        "inputs": [
            {
                "name": "ibmcloud_api_key",
                "type": "string",
                "description": "The IBM Cloud API Key",
                "default": "",
                "required": True,
            },
            {
                "name": "region",
                "type": "string",
                "description": "Region to provision resources",
                "default": "us-south",
                "required": False,
            },
            {
                "name": "prefix",
                "type": "string",
                "description": "Prefix for resource names",
                "default": "vpc-basic",
                "required": False,
            },
        ],
        "outputs": [
            {"name": "vpc_id", "description": "The ID of the created VPC"},
            {"name": "subnet_ids", "description": "List of subnet IDs"},
        ],
        "dependencies": [
            {
                "name": "resource_group",
                "source": "terraform-ibm-modules/resource-group/ibm",
                "version": "1.2.0",
            }
        ],
        "provider_dependencies": [
            {
                "name": "ibm",
                "source": "IBM-Cloud/ibm",
                "version": ">= 1.64.0",
            }
        ],
        "resources": [
            {"name": "vpc", "type": "ibm_is_vpc"},
            {"name": "subnet", "type": "ibm_is_subnet"},
        ],
    }


def test_format_example_inputs():
    """Test formatting of example inputs."""
    inputs = [
        {
            "name": "api_key",
            "type": "string",
            "description": "API key for authentication",
            "required": True,
        },
        {
            "name": "region",
            "type": "string",
            "description": "Deployment region",
            "default": "us-south",
            "required": False,
        },
    ]

    required, optional = format_example_inputs(inputs)

    assert "**api_key**" in required
    assert "string" in required
    assert "API key for authentication" in required

    assert "**region**" in optional
    assert "default: `us-south`" in optional


def test_format_example_inputs_empty():
    """Test formatting with no inputs."""
    required, optional = format_example_inputs([])

    assert required == "None"
    assert optional == "None"


def test_format_example_outputs():
    """Test formatting of example outputs."""
    outputs = [
        {"name": "vpc_id", "description": "VPC identifier"},
        {"name": "subnet_ids", "description": "List of subnet IDs"},
    ]

    result = format_example_outputs(outputs)

    assert "**vpc_id**" in result
    assert "VPC identifier" in result
    assert "**subnet_ids**" in result
    assert "List of subnet IDs" in result


def test_format_example_outputs_empty():
    """Test formatting with no outputs."""
    result = format_example_outputs([])
    assert result == "None"


def test_format_example_dependencies():
    """Test formatting of example dependencies."""
    provider_deps = [
        {"name": "ibm", "source": "IBM-Cloud/ibm", "version": ">= 1.64.0"},
        {"name": "tls", "source": "hashicorp/tls", "version": ">= 4.0.4"},
    ]

    module_deps = [
        {
            "name": "resource_group",
            "source": "terraform-ibm-modules/resource-group/ibm",
            "version": "1.2.0",
        }
    ]

    provider_text, module_text = format_example_dependencies(provider_deps, module_deps)

    assert "**ibm**" in provider_text
    assert "IBM-Cloud/ibm" in provider_text
    assert ">= 1.64.0" in provider_text

    assert "**resource_group**" in module_text
    assert "terraform-ibm-modules/resource-group/ibm" in module_text
    assert "1.2.0" in module_text


def test_format_example_dependencies_empty():
    """Test formatting with no dependencies."""
    provider_text, module_text = format_example_dependencies([], [])

    assert provider_text == "None"
    assert module_text == "None"


def test_format_example_resources():
    """Test formatting of example resources."""
    resources = [
        {"name": "vpc", "type": "ibm_is_vpc"},
        {"name": "subnet", "type": "ibm_is_subnet"},
    ]

    result = format_example_resources(resources)

    assert "**vpc**" in result
    assert "`ibm_is_vpc`" in result
    assert "**subnet**" in result
    assert "`ibm_is_subnet`" in result


def test_format_example_resources_empty():
    """Test formatting with no resources."""
    result = format_example_resources([])
    assert result == "None"


def test_format_example_details(sample_example_data):
    """Test formatting of complete example details."""
    result = format_example_details(
        sample_example_data, "terraform-ibm-modules/vpc/ibm", "1.5.2"
    )

    # Check header
    assert "# terraform-ibm-modules/vpc/ibm - Example: basic" in result
    assert "**Path:** `examples/basic`" in result
    assert "**Version:** v1.5.2" in result

    # Check sections are present
    assert "## Description" in result
    assert "## Required Inputs" in result
    assert "## Optional Inputs" in result
    assert "## Outputs" in result
    assert "## Dependencies" in result
    assert "## Resources Created" in result
    assert "## Full README" in result

    # Check content
    assert "ibmcloud_api_key" in result
    assert "vpc_id" in result
    assert "ibm_is_vpc" in result


def test_format_example_details_missing_path():
    """Test formatting with missing path raises error."""
    with pytest.raises(ValueError, match="path is required"):
        format_example_details({}, "terraform-ibm-modules/vpc/ibm", "1.5.2")


@pytest.mark.asyncio
async def test_get_example_details_impl_success():
    """Test successful example details retrieval."""
    request = GetExampleDetailsRequest(
        module_id="terraform-ibm-modules/vpc/ibm", example_path="examples/basic"
    )
    config = Config()

    # This will make a real API call
    result = await get_example_details_impl(request, config)

    # Verify structure
    assert "# terraform-ibm-modules/vpc/ibm - Example:" in result
    assert "**Path:** `examples/basic`" in result
    assert "## Description" in result
    assert "## Required Inputs" in result
    assert "## Outputs" in result


@pytest.mark.asyncio
async def test_get_example_details_impl_with_version():
    """Test example details retrieval with specific version."""
    request = GetExampleDetailsRequest(
        module_id="terraform-ibm-modules/vpc/ibm/1.5.2", example_path="examples/basic"
    )
    config = Config()

    result = await get_example_details_impl(request, config)

    assert "**Version:** v1.5.2" in result
    assert "examples/basic" in result


@pytest.mark.asyncio
async def test_get_example_details_impl_invalid_module():
    """Test example details retrieval with invalid module."""
    request = GetExampleDetailsRequest(
        module_id="nonexistent/module/provider", example_path="examples/basic"
    )
    config = Config()

    with pytest.raises(ModuleNotFoundError):
        await get_example_details_impl(request, config)


@pytest.mark.asyncio
async def test_get_example_details_impl_invalid_example():
    """Test example details retrieval with invalid example path."""
    request = GetExampleDetailsRequest(
        module_id="terraform-ibm-modules/vpc/ibm",
        example_path="examples/nonexistent",
    )
    config = Config()

    with pytest.raises(ModuleNotFoundError):
        await get_example_details_impl(request, config)


@pytest.mark.asyncio
async def test_get_example_details_impl_invalid_module_id():
    """Test example details retrieval with invalid module ID format."""
    request = GetExampleDetailsRequest(
        module_id="invalid-format", example_path="examples/basic"
    )
    config = Config()

    with pytest.raises(TerraformRegistryError, match="validation failed"):
        await get_example_details_impl(request, config)