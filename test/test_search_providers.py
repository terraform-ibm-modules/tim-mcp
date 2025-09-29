"""
Tests for the search_providers tool implementation.

Following TDD methodology - these tests define the behavior we want to implement.
"""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from tim_mcp.config import Config
from tim_mcp.exceptions import RateLimitError, TerraformRegistryError
from tim_mcp.exceptions import ValidationError as TIMValidationError
from tim_mcp.tools.search_providers import search_providers_impl
from tim_mcp.types import ProviderInfo, ProviderSearchRequest, ProviderSearchResponse


class TestSearchProvidersImpl:
    """Test the search_providers_impl function."""

    @pytest.fixture
    def config(self):
        """Create a test configuration."""
        return Config()

    @pytest.fixture
    def mock_terraform_client(self):
        """Create a mock Terraform client."""
        client = AsyncMock()
        return client

    @pytest.fixture
    def sample_registry_response(self):
        """Sample response from Terraform Registry API."""
        return {
            "providers": [
                {
                    "id": "hashicorp/aws/6.14.1",
                    "namespace": "hashicorp",
                    "name": "aws",
                    "version": "6.14.1",
                    "description": "terraform-provider-aws",
                    "source": "https://github.com/hashicorp/terraform-provider-aws",
                    "downloads": 4966945606,
                    "tier": "official",
                    "published_at": "2025-09-22T17:13:05Z",
                },
                {
                    "id": "hashicorp/azurerm/4.8.0",
                    "namespace": "hashicorp",
                    "name": "azurerm",
                    "version": "4.8.0",
                    "description": "terraform-provider-azurerm",
                    "source": "https://github.com/hashicorp/terraform-provider-azurerm",
                    "downloads": 3500000000,
                    "tier": "official",
                    "published_at": "2025-09-20T10:00:00Z",
                },
            ],
            "meta": {
                "limit": 10,
                "current_offset": 0,
                "next_offset": 10,
            },
        }

    @pytest.fixture
    def expected_response(self):
        """Expected formatted response."""
        return ProviderSearchResponse(
            query="aws",
            total_found=2,
            limit=10,
            offset=0,
            providers=[
                ProviderInfo(
                    id="hashicorp/aws/6.14.1",
                    namespace="hashicorp",
                    name="aws",
                    version="6.14.1",
                    description="terraform-provider-aws",
                    source_url="https://github.com/hashicorp/terraform-provider-aws",
                    downloads=4966945606,
                    tier="official",
                    published_at=datetime.fromisoformat("2025-09-22T17:13:05+00:00"),
                ),
                ProviderInfo(
                    id="hashicorp/azurerm/4.8.0",
                    namespace="hashicorp",
                    name="azurerm",
                    version="4.8.0",
                    description="terraform-provider-azurerm",
                    source_url="https://github.com/hashicorp/terraform-provider-azurerm",
                    downloads=3500000000,
                    tier="official",
                    published_at=datetime.fromisoformat("2025-09-20T10:00:00+00:00"),
                ),
            ],
        )

    @pytest.mark.asyncio
    async def test_successful_search_with_query(
        self, config, mock_terraform_client, sample_registry_response, expected_response
    ):
        """Test successful provider search with query."""
        # Setup
        mock_terraform_client.search_providers.return_value = sample_registry_response
        request = ProviderSearchRequest(query="aws", limit=10, offset=0)

        with patch("tim_mcp.tools.search_providers.TerraformClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = (
                mock_terraform_client
            )

            # Execute
            result = await search_providers_impl(request, config)

            # Verify
            assert result == expected_response
            mock_terraform_client.search_providers.assert_called_once_with(
                query="aws", limit=10, offset=0
            )

    @pytest.mark.asyncio
    async def test_successful_search_without_query(
        self, config, mock_terraform_client, sample_registry_response
    ):
        """Test successful provider search without query (list all)."""
        # Setup
        mock_terraform_client.search_providers.return_value = sample_registry_response
        request = ProviderSearchRequest(query=None, limit=10, offset=0)

        with patch("tim_mcp.tools.search_providers.TerraformClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = (
                mock_terraform_client
            )

            # Execute
            result = await search_providers_impl(request, config)

            # Verify
            assert result.query is None
            assert result.total_found == 2
            assert len(result.providers) == 2
            mock_terraform_client.search_providers.assert_called_once_with(
                query=None, limit=10, offset=0
            )

    @pytest.mark.asyncio
    async def test_successful_search_with_pagination(
        self, config, mock_terraform_client, sample_registry_response
    ):
        """Test successful provider search with pagination parameters."""
        # Setup
        mock_terraform_client.search_providers.return_value = sample_registry_response
        request = ProviderSearchRequest(query="hashicorp", limit=20, offset=10)

        with patch("tim_mcp.tools.search_providers.TerraformClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = (
                mock_terraform_client
            )

            # Execute
            result = await search_providers_impl(request, config)

            # Verify
            assert result.query == "hashicorp"
            assert result.limit == 20
            assert result.offset == 10
            mock_terraform_client.search_providers.assert_called_once_with(
                query="hashicorp", limit=20, offset=10
            )

    @pytest.mark.asyncio
    async def test_empty_search_results(self, config, mock_terraform_client):
        """Test handling of empty search results."""
        # Setup
        empty_response = {
            "providers": [],
            "meta": {"limit": 10, "current_offset": 0},
        }
        mock_terraform_client.search_providers.return_value = empty_response
        request = ProviderSearchRequest(query="nonexistent")

        with patch("tim_mcp.tools.search_providers.TerraformClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = (
                mock_terraform_client
            )

            # Execute
            result = await search_providers_impl(request, config)

            # Verify
            assert result.query == "nonexistent"
            assert result.total_found == 0
            assert result.providers == []

    @pytest.mark.asyncio
    async def test_terraform_registry_error(self, config, mock_terraform_client):
        """Test handling of Terraform Registry API errors."""
        # Setup
        mock_terraform_client.search_providers.side_effect = TerraformRegistryError(
            "API temporarily unavailable", status_code=503
        )
        request = ProviderSearchRequest(query="aws")

        with patch("tim_mcp.tools.search_providers.TerraformClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = (
                mock_terraform_client
            )

            # Execute & Verify
            with pytest.raises(TerraformRegistryError) as exc_info:
                await search_providers_impl(request, config)

            assert "API temporarily unavailable" in str(exc_info.value)
            assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_rate_limit_error(self, config, mock_terraform_client):
        """Test handling of rate limit errors."""
        # Setup
        mock_terraform_client.search_providers.side_effect = RateLimitError(
            "Rate limit exceeded", reset_time=1695123456, api_name="Terraform Registry"
        )
        request = ProviderSearchRequest(query="aws")

        with patch("tim_mcp.tools.search_providers.TerraformClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = (
                mock_terraform_client
            )

            # Execute & Verify
            with pytest.raises(RateLimitError) as exc_info:
                await search_providers_impl(request, config)

            assert "Rate limit exceeded" in str(exc_info.value)
            assert exc_info.value.reset_time == 1695123456

    @pytest.mark.asyncio
    async def test_malformed_api_response(self, config, mock_terraform_client):
        """Test handling of malformed API responses - invalid providers are skipped."""
        # Setup - provider with missing required fields
        malformed_response = {
            "providers": [
                {
                    "id": "hashicorp/aws/6.14.1",
                    "namespace": "hashicorp",
                    # Missing required fields like 'name', 'version', etc.
                }
            ],
            "meta": {"limit": 10, "current_offset": 0},
        }
        mock_terraform_client.search_providers.return_value = malformed_response
        request = ProviderSearchRequest(query="aws")

        with patch("tim_mcp.tools.search_providers.TerraformClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = (
                mock_terraform_client
            )

            # Execute - should handle malformed data gracefully
            result = await search_providers_impl(request, config)

            # Verify - no providers should be in results since all were invalid
            assert len(result.providers) == 0
            assert result.total_found == 0

    @pytest.mark.asyncio
    async def test_invalid_datetime_format(self, config, mock_terraform_client):
        """Test handling of invalid datetime formats - providers with bad dates are skipped."""
        # Setup
        invalid_datetime_response = {
            "providers": [
                {
                    "id": "test/bad-date/1.0.0",
                    "namespace": "test",
                    "name": "bad-date",
                    "version": "1.0.0",
                    "description": "Test provider",
                    "source": "https://github.com/test/provider",
                    "downloads": 123,
                    "tier": "community",
                    "published_at": "invalid-date-format",
                },
                {  # Valid provider
                    "id": "hashicorp/aws/6.14.1",
                    "namespace": "hashicorp",
                    "name": "aws",
                    "version": "6.14.1",
                    "description": "terraform-provider-aws",
                    "source": "https://github.com/hashicorp/terraform-provider-aws",
                    "downloads": 100,
                    "tier": "official",
                    "published_at": "2025-01-01T00:00:00Z",
                },
            ],
            "meta": {"limit": 10, "current_offset": 0},
        }
        mock_terraform_client.search_providers.return_value = invalid_datetime_response
        request = ProviderSearchRequest(query="test")

        with patch("tim_mcp.tools.search_providers.TerraformClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = (
                mock_terraform_client
            )

            # Execute - should handle invalid datetime gracefully
            result = await search_providers_impl(request, config)

            # Verify - only the valid provider should be in results
            assert len(result.providers) == 1
            assert result.providers[0].id == "hashicorp/aws/6.14.1"

    @pytest.mark.asyncio
    async def test_missing_meta_information(self, config, mock_terraform_client):
        """Test handling of missing meta information in API response."""
        # Setup
        no_meta_response = {
            "providers": []
            # Missing 'meta' section
        }
        mock_terraform_client.search_providers.return_value = no_meta_response
        request = ProviderSearchRequest(query="aws")

        with patch("tim_mcp.tools.search_providers.TerraformClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = (
                mock_terraform_client
            )

            # Execute & Verify
            with pytest.raises(TIMValidationError) as exc_info:
                await search_providers_impl(request, config)

            assert "Invalid API response format" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_download_sorting(self, config, mock_terraform_client):
        """Test that results are sorted by downloads in descending order."""
        # Setup - providers in wrong download order
        unsorted_response = {
            "providers": [
                {
                    "id": "low/downloads/1.0.0",
                    "namespace": "low",
                    "name": "downloads",
                    "version": "1.0.0",
                    "description": "Provider with few downloads",
                    "source": "https://github.com/low/provider",
                    "downloads": 100,
                    "tier": "community",
                    "published_at": "2025-09-01T08:00:00Z",
                },
                {
                    "id": "hashicorp/aws/6.14.1",
                    "namespace": "hashicorp",
                    "name": "aws",
                    "version": "6.14.1",
                    "description": "terraform-provider-aws",
                    "source": "https://github.com/hashicorp/terraform-provider-aws",
                    "downloads": 4966945606,
                    "tier": "official",
                    "published_at": "2025-09-22T17:13:05Z",
                },
                {
                    "id": "medium/downloads/1.5.0",
                    "namespace": "medium",
                    "name": "downloads",
                    "version": "1.5.0",
                    "description": "Provider with medium downloads",
                    "source": "https://github.com/medium/provider",
                    "downloads": 5000,
                    "tier": "partner",
                    "published_at": "2025-09-01T12:00:00Z",
                },
            ],
            "meta": {"limit": 100, "current_offset": 0},
        }
        mock_terraform_client.search_providers.return_value = unsorted_response
        request = ProviderSearchRequest(query="providers")

        with patch("tim_mcp.tools.search_providers.TerraformClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = (
                mock_terraform_client
            )

            # Execute
            result = await search_providers_impl(request, config)

            # Verify that results are sorted by downloads descending
            assert result.query == "providers"
            assert result.total_found == 3
            assert len(result.providers) == 3

            # Check order: high (4966945606) -> medium (5000) -> low (100)
            assert result.providers[0].downloads == 4966945606
            assert result.providers[0].id == "hashicorp/aws/6.14.1"
            assert result.providers[1].downloads == 5000
            assert result.providers[1].id == "medium/downloads/1.5.0"
            assert result.providers[2].downloads == 100
            assert result.providers[2].id == "low/downloads/1.0.0"


class TestProviderSearchRequestValidation:
    """Test validation of ProviderSearchRequest."""

    def test_valid_request_with_query(self):
        """Test valid request creation with query."""
        request = ProviderSearchRequest(query="aws", limit=10, offset=0)
        assert request.query == "aws"
        assert request.limit == 10
        assert request.offset == 0

    def test_valid_request_without_query(self):
        """Test valid request creation without query."""
        request = ProviderSearchRequest(query=None, limit=20)
        assert request.query is None
        assert request.limit == 20
        assert request.offset == 0

    def test_default_values(self):
        """Test default values are applied."""
        request = ProviderSearchRequest()
        assert request.query is None
        assert request.limit == 10
        assert request.offset == 0

    def test_limit_validation_min(self):
        """Test limit minimum validation."""
        with pytest.raises(ValidationError):
            ProviderSearchRequest(limit=0)

    def test_limit_validation_max(self):
        """Test limit maximum validation."""
        with pytest.raises(ValidationError):
            ProviderSearchRequest(limit=101)

    def test_offset_validation_negative(self):
        """Test offset cannot be negative."""
        with pytest.raises(ValidationError):
            ProviderSearchRequest(offset=-1)


class TestProviderInfoValidation:
    """Test validation of ProviderInfo model."""

    def test_valid_provider_info(self):
        """Test valid ProviderInfo creation."""
        provider = ProviderInfo(
            id="hashicorp/aws/6.14.1",
            namespace="hashicorp",
            name="aws",
            version="6.14.1",
            description="terraform-provider-aws",
            source_url="https://github.com/hashicorp/terraform-provider-aws",
            downloads=4966945606,
            tier="official",
            published_at=datetime.now(),
        )
        assert provider.id == "hashicorp/aws/6.14.1"
        assert provider.downloads == 4966945606
        assert provider.tier == "official"

    def test_invalid_source_url(self):
        """Test invalid source URL validation."""
        with pytest.raises(ValidationError):
            ProviderInfo(
                id="test/provider/1.0.0",
                namespace="test",
                name="provider",
                version="1.0.0",
                description="Test description",
                source_url="not-a-url",
                downloads=100,
                tier="community",
                published_at=datetime.now(),
            )

    def test_negative_downloads(self):
        """Test negative downloads validation."""
        with pytest.raises(ValidationError):
            ProviderInfo(
                id="test/provider/1.0.0",
                namespace="test",
                name="provider",
                version="1.0.0",
                description="Test description",
                source_url="https://github.com/test/repo",
                downloads=-1,
                tier="community",
                published_at=datetime.now(),
            )