"""Tests for the get_latest_module_version tool implementation."""

from unittest.mock import AsyncMock, patch

import pytest

from tim_mcp.config import Config
from tim_mcp.exceptions import ModuleNotFoundError, TerraformRegistryError
from tim_mcp.types import LatestModuleVersionRequest


@pytest.fixture
def config():
    """Create a test configuration."""
    return Config()


class TestGetLatestModuleVersion:
    @pytest.mark.asyncio
    async def test_get_latest_module_version_with_release(self, config):
        """Returns latest version and release metadata when a GitHub release exists."""
        from tim_mcp.tools.latest_version import get_latest_module_version_impl

        with (
            patch("tim_mcp.tools.latest_version.TerraformClient") as mock_tf_class,
            patch("tim_mcp.tools.latest_version.GitHubClient") as mock_gh_class,
        ):
            mock_tf_client = AsyncMock()
            mock_tf_class.return_value.__aenter__.return_value = mock_tf_client
            mock_tf_client.get_module_versions.return_value = ["7.4.2", "7.4.1"]

            mock_gh_client = AsyncMock()
            mock_gh_class.return_value.__aenter__.return_value = mock_gh_client
            mock_gh_client.get_latest_release.return_value = {
                "tag_name": "v7.4.2",
                "name": "Release v7.4.2",
                "published_at": "2025-09-02T10:30:00.000Z",
                "html_url": "https://github.com/terraform-ibm-modules/terraform-ibm-vpc/releases/tag/v7.4.2",
                "body": "Bug fixes and documentation updates.",
            }

            request = LatestModuleVersionRequest(
                module_id="terraform-ibm-modules/vpc/ibm"
            )
            result = await get_latest_module_version_impl(request, config)

            assert "# terraform-ibm-modules/vpc/ibm - Latest Version" in result
            assert "**Latest Version:** v7.4.2" in result
            assert "**Release Tag:** v7.4.2" in result
            assert "**Release Name:** Release v7.4.2" in result
            assert "**Published:** 2025-09-02" in result
            assert "**Release URL:** https://github.com/terraform-ibm-modules/terraform-ibm-vpc/releases/tag/v7.4.2" in result
            assert "## Release Notes" in result
            assert "Bug fixes and documentation updates." in result

            mock_tf_client.get_module_versions.assert_called_once_with(
                namespace="terraform-ibm-modules",
                name="vpc",
                provider="ibm",
            )
            mock_gh_client.get_latest_release.assert_called_once_with(
                owner="terraform-ibm-modules",
                repo="terraform-ibm-vpc",
            )

    @pytest.mark.asyncio
    async def test_get_latest_module_version_without_release(self, config):
        """Returns latest version even when no GitHub release exists."""
        from tim_mcp.tools.latest_version import get_latest_module_version_impl

        with (
            patch("tim_mcp.tools.latest_version.TerraformClient") as mock_tf_class,
            patch("tim_mcp.tools.latest_version.GitHubClient") as mock_gh_class,
        ):
            mock_tf_client = AsyncMock()
            mock_tf_class.return_value.__aenter__.return_value = mock_tf_client
            mock_tf_client.get_module_versions.return_value = ["1.2.3"]

            mock_gh_client = AsyncMock()
            mock_gh_class.return_value.__aenter__.return_value = mock_gh_client
            mock_gh_client.get_latest_release.side_effect = ModuleNotFoundError(
                "terraform-ibm-modules/example"
            )

            request = LatestModuleVersionRequest(module_id="terraform-ibm-modules/example/ibm")
            result = await get_latest_module_version_impl(request, config)

            assert "**Latest Version:** v1.2.3" in result
            assert "**Release Information:** Not available" in result

    @pytest.mark.asyncio
    async def test_get_latest_module_version_no_versions_found(self, config):
        """Raises module not found when the registry returns no versions."""
        from tim_mcp.tools.latest_version import get_latest_module_version_impl

        with patch("tim_mcp.tools.latest_version.TerraformClient") as mock_tf_class:
            mock_tf_client = AsyncMock()
            mock_tf_class.return_value.__aenter__.return_value = mock_tf_client
            mock_tf_client.get_module_versions.return_value = []

            request = LatestModuleVersionRequest(module_id="terraform-ibm-modules/missing/ibm")

            with pytest.raises(ModuleNotFoundError):
                await get_latest_module_version_impl(request, config)

    @pytest.mark.asyncio
    async def test_get_latest_module_version_invalid_module_id(self, config):
        """Converts invalid module IDs to a registry error."""
        from tim_mcp.tools.latest_version import get_latest_module_version_impl

        request = LatestModuleVersionRequest(module_id="invalid-module-id")

        with pytest.raises(TerraformRegistryError, match="Module ID validation failed"):
            await get_latest_module_version_impl(request, config)
