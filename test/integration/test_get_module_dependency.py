"""
Tests for the get_module_dependency tool implementation.
"""

from unittest.mock import AsyncMock, patch

import pytest

from tim_mcp.config import Config
from tim_mcp.exceptions import (
    ModuleNotFoundError,
    RateLimitError,
    TerraformRegistryError,
)
from tim_mcp.types import ModuleDependencyRequest


@pytest.fixture
def config():
    """Create a test configuration."""
    return Config()


@pytest.fixture
def sample_module_data():
    """Sample API response with root and submodule dependencies."""
    return {
        "id": "terraform-ibm-modules/vpc/ibm",
        "version": "7.4.2",
        "root": {
            "dependencies": [
                {
                    "name": "vpc",
                    "version": "v4.0.0",
                    "source": "terraform-ibm-modules/vpc/ibm",
                }
            ],
            "provider_dependencies": [
                {
                    "name": "ibm",
                    "namespace": "IBM-Cloud",
                    "version": ">= 1.70.1, < 3.0.0",
                }
            ],
        },
        "submodules": [
            {
                "path": "modules/subnet",
                "dependencies": [],
                "provider_dependencies": [
                    {
                        "name": "ibm",
                        "namespace": "IBM-Cloud",
                        "version": ">= 1.70.1, < 3.0.0",
                    }
                ],
            }
        ],
    }


@pytest.fixture
def sample_module_data_no_deps():
    """Sample API response with no dependencies."""
    return {
        "id": "simple/module/aws",
        "version": "1.0.0",
        "root": {
            "dependencies": [],
            "provider_dependencies": [],
        },
        "submodules": [],
    }


class TestGetModuleDependencySuccess:
    """Test successful dependency retrieval."""

    @pytest.mark.asyncio
    async def test_returns_markdown_string(self, config, sample_module_data):
        """Test that the tool returns a non-empty markdown string."""
        from tim_mcp.tools.dependency import get_module_dependency_impl

        with patch("tim_mcp.tools.dependency.TerraformClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.get_module_details.return_value = sample_module_data

            request = ModuleDependencyRequest(module_id="terraform-ibm-modules/vpc/ibm")
            result = await get_module_dependency_impl(request, config)

        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_output_contains_module_id_and_version(
        self, config, sample_module_data
    ):
        """Test that the output header includes the module ID and version."""
        from tim_mcp.tools.dependency import get_module_dependency_impl

        with patch("tim_mcp.tools.dependency.TerraformClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.get_module_details.return_value = sample_module_data

            request = ModuleDependencyRequest(module_id="terraform-ibm-modules/vpc/ibm")
            result = await get_module_dependency_impl(request, config)

        assert "terraform-ibm-modules/vpc/ibm" in result
        assert "7.4.2" in result

    @pytest.mark.asyncio
    async def test_output_contains_provider_requirements(
        self, config, sample_module_data
    ):
        """Test that root provider requirements appear in the output."""
        from tim_mcp.tools.dependency import get_module_dependency_impl

        with patch("tim_mcp.tools.dependency.TerraformClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.get_module_details.return_value = sample_module_data

            request = ModuleDependencyRequest(module_id="terraform-ibm-modules/vpc/ibm")
            result = await get_module_dependency_impl(request, config)

        assert "Provider Requirements" in result
        assert ">= 1.70.1, < 3.0.0" in result

    @pytest.mark.asyncio
    async def test_output_contains_module_dependencies(
        self, config, sample_module_data
    ):
        """Test that root module dependencies appear in the output."""
        from tim_mcp.tools.dependency import get_module_dependency_impl

        with patch("tim_mcp.tools.dependency.TerraformClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.get_module_details.return_value = sample_module_data

            request = ModuleDependencyRequest(module_id="terraform-ibm-modules/vpc/ibm")
            result = await get_module_dependency_impl(request, config)

        assert "Module Dependencies" in result
        assert "vpc" in result

    @pytest.mark.asyncio
    async def test_output_contains_submodule_section(self, config, sample_module_data):
        """Test that submodule dependency sections are present."""
        from tim_mcp.tools.dependency import get_module_dependency_impl

        with patch("tim_mcp.tools.dependency.TerraformClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.get_module_details.return_value = sample_module_data

            request = ModuleDependencyRequest(module_id="terraform-ibm-modules/vpc/ibm")
            result = await get_module_dependency_impl(request, config)

        assert "Submodule" in result
        assert "modules/subnet" in result

    @pytest.mark.asyncio
    async def test_no_dependencies_renders_none(
        self, config, sample_module_data_no_deps
    ):
        """Test that modules with no dependencies display 'None' placeholders."""
        from tim_mcp.tools.dependency import get_module_dependency_impl

        with patch("tim_mcp.tools.dependency.TerraformClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.get_module_details.return_value = sample_module_data_no_deps

            request = ModuleDependencyRequest(module_id="simple/module/aws")
            result = await get_module_dependency_impl(request, config)

        assert "None" in result

    @pytest.mark.asyncio
    async def test_specific_version_passed_to_client(self, config, sample_module_data):
        """Test that a pinned version is forwarded to the Terraform client."""
        from tim_mcp.tools.dependency import get_module_dependency_impl

        versioned_data = {**sample_module_data, "version": "7.4.1"}

        with patch("tim_mcp.tools.dependency.TerraformClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.get_module_details.return_value = versioned_data

            request = ModuleDependencyRequest(
                module_id="terraform-ibm-modules/vpc/ibm/7.4.1"
            )
            await get_module_dependency_impl(request, config)

            mock_client.get_module_details.assert_called_once_with(
                namespace="terraform-ibm-modules",
                name="vpc",
                provider="ibm",
                version="7.4.1",
            )

    @pytest.mark.asyncio
    async def test_latest_version_passed_to_client(self, config, sample_module_data):
        """Test that omitting version results in 'latest' being passed to the client."""
        from tim_mcp.tools.dependency import get_module_dependency_impl

        with patch("tim_mcp.tools.dependency.TerraformClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.get_module_details.return_value = sample_module_data

            request = ModuleDependencyRequest(module_id="terraform-ibm-modules/vpc/ibm")
            await get_module_dependency_impl(request, config)

            mock_client.get_module_details.assert_called_once_with(
                namespace="terraform-ibm-modules",
                name="vpc",
                provider="ibm",
                version="latest",
            )


class TestGetModuleDependencyErrors:
    """Test error handling for get_module_dependency."""

    @pytest.mark.asyncio
    async def test_module_not_found_raises_module_not_found_error(self, config):
        """Test that a 404 from the registry is translated to ModuleNotFoundError."""
        from tim_mcp.tools.dependency import get_module_dependency_impl

        with patch("tim_mcp.tools.dependency.TerraformClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.get_module_details.side_effect = TerraformRegistryError(
                "Module not found", status_code=404
            )

            request = ModuleDependencyRequest(module_id="nonexistent/module/ibm")

            with pytest.raises(ModuleNotFoundError) as exc_info:
                await get_module_dependency_impl(request, config)

        assert "nonexistent/module/ibm" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_registry_error_is_reraised(self, config):
        """Test that non-404 registry errors are re-raised unchanged."""
        from tim_mcp.tools.dependency import get_module_dependency_impl

        with patch("tim_mcp.tools.dependency.TerraformClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.get_module_details.side_effect = TerraformRegistryError(
                "Internal server error", status_code=500
            )

            request = ModuleDependencyRequest(module_id="test/module/ibm")

            with pytest.raises(TerraformRegistryError) as exc_info:
                await get_module_dependency_impl(request, config)

        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_rate_limit_error_is_reraised(self, config):
        """Test that rate limit errors propagate to the caller."""
        from tim_mcp.tools.dependency import get_module_dependency_impl

        with patch("tim_mcp.tools.dependency.TerraformClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.get_module_details.side_effect = RateLimitError(
                "Rate limit exceeded", reset_time=1640995200
            )

            request = ModuleDependencyRequest(module_id="test/module/ibm")

            with pytest.raises(RateLimitError):
                await get_module_dependency_impl(request, config)

    @pytest.mark.asyncio
    async def test_invalid_module_id_raises_terraform_registry_error(self, config):
        """Test that a malformed module_id raises TerraformRegistryError."""
        from tim_mcp.tools.dependency import get_module_dependency_impl

        request = ModuleDependencyRequest(module_id="invalid-format")

        with pytest.raises(TerraformRegistryError) as exc_info:
            await get_module_dependency_impl(request, config)

        assert "validation" in str(exc_info.value).lower()


class TestFormatModuleDependencies:
    """Unit tests for the format_module_dependencies formatter."""

    def test_format_includes_root_module_section(self):
        """Test that the root module section is always present."""
        from tim_mcp.tools.dependency import format_module_dependencies

        data = {
            "id": "test/module/ibm",
            "version": "1.0.0",
            "root": {"dependencies": [], "provider_dependencies": []},
            "submodules": [],
        }

        result = format_module_dependencies(data)

        assert "## Root Module" in result

    def test_format_submodules_none_when_empty(self):
        """Test that '_None_' is rendered when there are no submodules."""
        from tim_mcp.tools.dependency import format_module_dependencies

        data = {
            "id": "test/module/ibm",
            "version": "1.0.0",
            "root": {"dependencies": [], "provider_dependencies": []},
            "submodules": [],
        }

        result = format_module_dependencies(data)

        assert "_None_" in result

    def test_format_submodule_path_in_output(self):
        """Test that each submodule path is included in its section header."""
        from tim_mcp.tools.dependency import format_module_dependencies

        data = {
            "id": "test/module/ibm",
            "version": "2.0.0",
            "root": {"dependencies": [], "provider_dependencies": []},
            "submodules": [
                {
                    "path": "modules/worker",
                    "dependencies": [],
                    "provider_dependencies": [],
                }
            ],
        }

        result = format_module_dependencies(data)

        assert "modules/worker" in result
