"""
Tests for the list_providers tool implementation.
"""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from tim_mcp.config import Config
from tim_mcp.exceptions import TIMError
from tim_mcp.tools.list_providers import (
    _fetch_provider,
    _matches_filter,
    _parse_provider_id,
    list_providers_impl,
)
from tim_mcp.types import ProviderInfo


class TestParseProviderId:
    """Test provider ID parsing."""

    def test_parse_valid_provider_id(self):
        """Test parsing valid provider ID."""
        result = _parse_provider_id("hashicorp/random")
        assert result == ("hashicorp", "random")

    def test_parse_provider_id_with_whitespace(self):
        """Test parsing provider ID with whitespace."""
        result = _parse_provider_id("  hashicorp/random  ")
        assert result == ("hashicorp", "random")

    def test_parse_invalid_provider_id_no_slash(self):
        """Test parsing invalid provider ID without slash."""
        result = _parse_provider_id("hashicorp-random")
        assert result is None

    def test_parse_invalid_provider_id_too_many_slashes(self):
        """Test parsing invalid provider ID with too many slashes."""
        result = _parse_provider_id("hashicorp/random/extra")
        assert result is None

    def test_parse_invalid_provider_id_empty_namespace(self):
        """Test parsing invalid provider ID with empty namespace."""
        result = _parse_provider_id("/random")
        assert result is None

    def test_parse_invalid_provider_id_empty_name(self):
        """Test parsing invalid provider ID with empty name."""
        result = _parse_provider_id("hashicorp/")
        assert result is None


class TestMatchesFilter:
    """Test filter matching."""

    @pytest.fixture
    def ibm_provider(self):
        """Create sample IBM provider."""
        return ProviderInfo(
            id="IBM-Cloud/ibm/1.83.2",
            namespace="IBM-Cloud",
            name="ibm",
            version="1.83.2",
            description="IBM Cloud Terraform Provider",
            source_url="https://github.com/IBM-Cloud/terraform-provider-ibm",
            downloads=10000000,
            tier="partner",
            published_at=datetime.now(),
        )

    @pytest.fixture
    def kubernetes_provider(self):
        """Create sample Kubernetes provider."""
        return ProviderInfo(
            id="hashicorp/kubernetes/2.23.0",
            namespace="hashicorp",
            name="kubernetes",
            version="2.23.0",
            description="Kubernetes Terraform Provider",
            source_url="https://github.com/hashicorp/terraform-provider-kubernetes",
            downloads=100000000,
            tier="official",
            published_at=datetime.now(),
        )

    def test_matches_filter_by_name(self, ibm_provider):
        """Test filter matches provider name."""
        assert _matches_filter(ibm_provider, "ibm")
        assert _matches_filter(ibm_provider, "IBM")
        assert _matches_filter(ibm_provider, "Ibm")

    def test_matches_filter_by_namespace(self, ibm_provider):
        """Test filter matches provider namespace."""
        assert _matches_filter(ibm_provider, "cloud")
        assert _matches_filter(ibm_provider, "IBM-Cloud")

    def test_matches_filter_by_description(self, kubernetes_provider):
        """Test filter matches provider description."""
        assert _matches_filter(kubernetes_provider, "Kubernetes")
        assert _matches_filter(kubernetes_provider, "terraform")

    def test_filter_no_match(self, ibm_provider):
        """Test filter doesn't match unrelated keyword."""
        assert not _matches_filter(ibm_provider, "azure")
        assert not _matches_filter(ibm_provider, "aws")


class TestFetchProvider:
    """Test fetching individual providers."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return Config()

    @pytest.fixture
    def mock_terraform_client(self):
        """Create mock Terraform client."""
        return AsyncMock()

    @pytest.fixture
    def ibm_provider_response(self):
        """Sample IBM provider API response."""
        return {
            "id": "IBM-Cloud/ibm/1.83.2",
            "namespace": "IBM-Cloud",
            "name": "ibm",
            "version": "1.83.2",
            "description": "IBM Cloud Terraform Provider",
            "source": "https://github.com/IBM-Cloud/terraform-provider-ibm",
            "downloads": 10000000,
            "tier": "partner",
            "published_at": "2025-09-01T12:00:00Z",
        }

    @pytest.mark.asyncio
    async def test_fetch_provider_success(
        self, mock_terraform_client, ibm_provider_response
    ):
        """Test successful provider fetch."""
        mock_terraform_client.get_provider_info.return_value = ibm_provider_response

        result = await _fetch_provider(mock_terraform_client, "IBM-Cloud", "ibm")

        assert result is not None
        assert result.namespace == "IBM-Cloud"
        assert result.name == "ibm"
        assert result.version == "1.83.2"
        assert result.downloads == 10000000

    @pytest.mark.asyncio
    async def test_fetch_provider_failure(self, mock_terraform_client):
        """Test provider fetch failure returns None."""
        mock_terraform_client.get_provider_info.side_effect = Exception("API error")

        result = await _fetch_provider(mock_terraform_client, "IBM-Cloud", "ibm")

        assert result is None


class TestListProvidersImpl:
    """Test list_providers_impl function."""

    @pytest.fixture
    def config(self):
        """Create test configuration with sample providers."""
        return Config()

    @pytest.fixture
    def mock_terraform_client(self):
        """Create mock Terraform client."""
        client = AsyncMock()
        return client

    @pytest.fixture
    def sample_providers_response(self):
        """Sample provider responses."""
        return [
            {
                "id": "ibm-cloud/ibm/1.83.2",
                "namespace": "ibm-cloud",
                "name": "ibm",
                "version": "1.83.2",
                "description": "IBM Cloud Terraform Provider",
                "source": "https://github.com/IBM-Cloud/terraform-provider-ibm",
                "downloads": 10000000,
                "tier": "partner",
                "published_at": "2025-09-01T12:00:00Z",
            },
            {
                "id": "hashicorp/random/3.5.1",
                "namespace": "hashicorp",
                "name": "random",
                "version": "3.5.1",
                "description": "Random Terraform Provider",
                "source": "https://github.com/hashicorp/terraform-provider-random",
                "downloads": 3500000000,
                "tier": "official",
                "published_at": "2025-09-20T10:00:00Z",
            },
            {
                "id": "hashicorp/kubernetes/2.23.0",
                "namespace": "hashicorp",
                "name": "kubernetes",
                "version": "2.23.0",
                "description": "Kubernetes Terraform Provider",
                "source": "https://github.com/hashicorp/terraform-provider-kubernetes",
                "downloads": 100000000,
                "tier": "official",
                "published_at": "2025-08-15T10:00:00Z",
            },
        ]

    @pytest.mark.asyncio
    async def test_list_providers_all(
        self, config, mock_terraform_client, sample_providers_response
    ):
        """Test listing all providers without filter."""

        # Mock get_provider_info to return different providers
        async def mock_get_provider_info(namespace, name):
            for provider in sample_providers_response:
                if provider["namespace"] == namespace and provider["name"] == name:
                    return provider
            raise Exception("Provider not found")

        mock_terraform_client.get_provider_info.side_effect = mock_get_provider_info

        with patch("tim_mcp.tools.list_providers.TerraformClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = (
                mock_terraform_client
            )

            result = await list_providers_impl(None, config)

            # Should return successfully fetched providers sorted by downloads
            # Only 3 providers in mock response, others will fail gracefully
            assert len(result) == 3
            # Check that results are sorted by downloads descending
            assert result[0].downloads == 3500000000  # random
            assert result[1].downloads == 100000000  # kubernetes
            assert result[2].downloads == 10000000  # ibm

    @pytest.mark.asyncio
    async def test_list_providers_with_filter(
        self, config, mock_terraform_client, sample_providers_response
    ):
        """Test listing providers with keyword filter."""

        async def mock_get_provider_info(namespace, name):
            for provider in sample_providers_response:
                if provider["namespace"] == namespace and provider["name"] == name:
                    return provider
            raise Exception("Provider not found")

        mock_terraform_client.get_provider_info.side_effect = mock_get_provider_info

        with patch("tim_mcp.tools.list_providers.TerraformClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = (
                mock_terraform_client
            )

            result = await list_providers_impl("ibm", config)

            # Should return only IBM provider
            assert len(result) == 1
            assert result[0].name == "ibm"
            assert result[0].namespace == "ibm-cloud"

    @pytest.mark.asyncio
    async def test_list_providers_kubernetes_filter(
        self, config, mock_terraform_client, sample_providers_response
    ):
        """Test filtering for kubernetes provider."""

        async def mock_get_provider_info(namespace, name):
            for provider in sample_providers_response:
                if provider["namespace"] == namespace and provider["name"] == name:
                    return provider
            raise Exception("Provider not found")

        mock_terraform_client.get_provider_info.side_effect = mock_get_provider_info

        with patch("tim_mcp.tools.list_providers.TerraformClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = (
                mock_terraform_client
            )

            result = await list_providers_impl("kubernetes", config)

            # Should return kubernetes provider
            assert len(result) == 1
            assert result[0].name == "kubernetes"

    @pytest.mark.asyncio
    async def test_list_providers_case_insensitive_filter(
        self, config, mock_terraform_client, sample_providers_response
    ):
        """Test filter is case-insensitive."""

        async def mock_get_provider_info(namespace, name):
            for provider in sample_providers_response:
                if provider["namespace"] == namespace and provider["name"] == name:
                    return provider
            raise Exception("Provider not found")

        mock_terraform_client.get_provider_info.side_effect = mock_get_provider_info

        with patch("tim_mcp.tools.list_providers.TerraformClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = (
                mock_terraform_client
            )

            result = await list_providers_impl("IBM", config)

            # Should find ibm provider despite case difference
            assert len(result) == 1
            assert result[0].name == "ibm"

    @pytest.mark.asyncio
    async def test_list_providers_no_matches(
        self, config, mock_terraform_client, sample_providers_response
    ):
        """Test filter with no matches returns empty list."""

        async def mock_get_provider_info(namespace, name):
            for provider in sample_providers_response:
                if provider["namespace"] == namespace and provider["name"] == name:
                    return provider
            raise Exception("Provider not found")

        mock_terraform_client.get_provider_info.side_effect = mock_get_provider_info

        with patch("tim_mcp.tools.list_providers.TerraformClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = (
                mock_terraform_client
            )

            result = await list_providers_impl("nonexistent", config)

            # Should return empty list
            assert len(result) == 0

    @pytest.mark.asyncio
    async def test_list_providers_partial_failure(
        self, config, mock_terraform_client, sample_providers_response
    ):
        """Test that partial fetch failures don't break entire list."""
        call_count = 0

        async def mock_get_provider_info(namespace, name):
            nonlocal call_count
            call_count += 1
            # Fail first call, succeed others
            if call_count == 1:
                raise Exception("API error")
            for provider in sample_providers_response:
                if provider["namespace"] == namespace and provider["name"] == name:
                    return provider
            raise Exception("Provider not found")

        mock_terraform_client.get_provider_info.side_effect = mock_get_provider_info

        with patch("tim_mcp.tools.list_providers.TerraformClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = (
                mock_terraform_client
            )

            result = await list_providers_impl(None, config)

            # Should succeed with remaining providers
            assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_list_providers_all_failures(self, config, mock_terraform_client):
        """Test that all fetch failures raises error."""
        mock_terraform_client.get_provider_info.side_effect = Exception("API error")

        with patch("tim_mcp.tools.list_providers.TerraformClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = (
                mock_terraform_client
            )

            with pytest.raises(TIMError) as exc_info:
                await list_providers_impl(None, config)

            assert "Failed to fetch any providers" in str(exc_info.value)
