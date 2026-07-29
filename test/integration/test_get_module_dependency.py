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
from tim_mcp.types import ModuleDetailsRequest


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
            "readme": (
                "## Requirements\n\n"
                "| Name | Version |\n"
                "|------|----------|\n"
                '| <a name="requirement_terraform"></a> [terraform](#requirement\\_terraform) | >= 1.9.0 |\n'
                '| <a name="requirement_ibm"></a> [ibm](#requirement\\_ibm) | >= 1.70.1, < 3.0.0 |\n'
                "\n## Providers\n"
            ),
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


class TestGetModuleDependencySuccess:
    """Test successful dependency retrieval."""

    @pytest.mark.asyncio
    async def test_output_contains_all_sections(self, config, sample_module_data):
        """Test that the output contains all expected sections and values."""
        from tim_mcp.tools.dependency import get_module_dependency_impl

        with patch("tim_mcp.tools.dependency.TerraformClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.get_module_details.return_value = sample_module_data

            request = ModuleDetailsRequest(module_id="terraform-ibm-modules/vpc/ibm")
            result = await get_module_dependency_impl(request, config)

        assert isinstance(result, str)
        # Header
        assert "terraform-ibm-modules/vpc/ibm" in result
        assert "7.4.2" in result
        # Terraform version requirement
        assert "## Requirements" in result
        assert "**Terraform Version:** >= 1.9.0" in result
        # Provider requirements
        assert "**Provider Requirements:**" in result
        assert ">= 1.70.1, < 3.0.0" in result
        # Module dependencies
        assert "**Module Dependencies:**" in result
        assert "vpc" in result
        # Submodule
        assert "## Submodule Dependencies" in result
        assert "modules/subnet" in result

    @pytest.mark.asyncio
    async def test_no_dependencies_renders_none(self, config):
        """Test that modules with no dependencies display 'None' in empty sections."""
        from tim_mcp.tools.dependency import get_module_dependency_impl

        no_deps_data = {
            "id": "simple/module/aws",
            "version": "1.0.0",
            "root": {"dependencies": [], "provider_dependencies": []},
            "submodules": [],
        }

        with patch("tim_mcp.tools.dependency.TerraformClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.get_module_details.return_value = no_deps_data

            request = ModuleDetailsRequest(module_id="simple/module/aws")
            result = await get_module_dependency_impl(request, config)

        assert "**Provider Requirements:**" in result
        assert "**Module Dependencies:**" in result
        assert "## Submodule Dependencies" in result
        assert "None" in result

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "module_id,expected_version",
        [
            ("terraform-ibm-modules/vpc/ibm/7.4.1", "7.4.1"),
            ("terraform-ibm-modules/vpc/ibm", "latest"),
        ],
    )
    async def test_version_forwarded_to_client(
        self, config, sample_module_data, module_id, expected_version
    ):
        """Test that the requested version (pinned or latest) is forwarded to the client."""
        from tim_mcp.tools.dependency import get_module_dependency_impl

        with patch("tim_mcp.tools.dependency.TerraformClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.get_module_details.return_value = sample_module_data

            await get_module_dependency_impl(
                ModuleDetailsRequest(module_id=module_id), config
            )

            mock_client.get_module_details.assert_called_once_with(
                namespace="terraform-ibm-modules",
                name="vpc",
                provider="ibm",
                version=expected_version,
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

            with pytest.raises(ModuleNotFoundError) as exc_info:
                await get_module_dependency_impl(
                    ModuleDetailsRequest(module_id="nonexistent/module/ibm"), config
                )

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

            with pytest.raises(TerraformRegistryError) as exc_info:
                await get_module_dependency_impl(
                    ModuleDetailsRequest(module_id="test/module/ibm"), config
                )

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

            with pytest.raises(RateLimitError):
                await get_module_dependency_impl(
                    ModuleDetailsRequest(module_id="test/module/ibm"), config
                )

    @pytest.mark.asyncio
    async def test_invalid_module_id_raises_terraform_registry_error(self, config):
        """Test that a malformed module_id raises TerraformRegistryError."""
        from tim_mcp.tools.dependency import get_module_dependency_impl

        with pytest.raises(TerraformRegistryError) as exc_info:
            await get_module_dependency_impl(
                ModuleDetailsRequest(module_id="invalid-format"), config
            )

        assert "validation" in str(exc_info.value).lower()


class TestFormatModuleDependencies:
    """Unit tests for the format_module_dependencies formatter."""

    def test_format_output_structure(self):
        """Test that all structural sections are always present and empty sections
        use fallback text instead of bare 'None' labels."""
        from tim_mcp.tools.dependency import format_module_dependencies

        data = {
            "id": "test/module/ibm",
            "version": "1.0.0",
            "root": {"dependencies": [], "provider_dependencies": []},
            "submodules": [],
        }

        result = format_module_dependencies(data)

        assert "## Requirements" in result
        assert "## Root Module" in result
        assert "## Submodule Dependencies" in result
        assert "**Provider Requirements:**" in result
        assert "**Module Dependencies:**" in result
        assert "None" in result

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

    def test_format_terraform_version_from_readme(self):
        """Test that the terraform version is extracted from the README and shown,
        and falls back to None when the README is absent or has no terraform row."""
        from tim_mcp.tools.dependency import format_module_dependencies

        # With a valid terraform row
        data_with_readme = {
            "id": "test/module/ibm",
            "version": "1.0.0",
            "root": {
                "readme": (
                    "## Requirements\n\n"
                    "| Name | Version |\n"
                    "|------|----------|\n"
                    '| <a name="requirement_terraform"></a> [terraform](#requirement\\_terraform) | >= 1.9.0 |\n'
                ),
                "dependencies": [],
                "provider_dependencies": [],
            },
            "submodules": [],
        }
        assert ">= 1.9.0" in format_module_dependencies(data_with_readme)

        # Without a readme at all — falls back to _None_ (italic markdown)
        data_no_readme = {
            "id": "test/module/ibm",
            "version": "1.0.0",
            "root": {"dependencies": [], "provider_dependencies": []},
            "submodules": [],
        }
        assert "**Terraform Version:** _None_" in format_module_dependencies(
            data_no_readme
        )
