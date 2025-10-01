"""
Tests for the get_provider_details tool implementation.

Following TDD methodology - these tests define the behavior we want to implement.
"""

from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from tim_mcp.config import Config
from tim_mcp.exceptions import TerraformRegistryError
from tim_mcp.exceptions import ValidationError as TIMValidationError
from tim_mcp.tools.get_provider_details import (
    format_provider_details,
    get_provider_details_impl,
    parse_provider_id_with_version,
)
from tim_mcp.types import ProviderDetailsRequest


class TestParseProviderIdWithVersion:
    """Test provider ID parsing functionality."""

    def test_parse_provider_without_version(self):
        """Test parsing provider ID without version (uses latest)."""
        namespace, name, version = parse_provider_id_with_version("hashicorp/aws")
        assert namespace == "hashicorp"
        assert name == "aws"
        assert version == "latest"

    def test_parse_provider_with_version(self):
        """Test parsing provider ID with specific version."""
        namespace, name, version = parse_provider_id_with_version(
            "hashicorp/aws/5.70.0"
        )
        assert namespace == "hashicorp"
        assert name == "aws"
        assert version == "5.70.0"

    def test_parse_provider_with_whitespace(self):
        """Test parsing provider ID with leading/trailing whitespace."""
        namespace, name, version = parse_provider_id_with_version("  hashicorp/aws  ")
        assert namespace == "hashicorp"
        assert name == "aws"
        assert version == "latest"

    def test_parse_invalid_provider_id_too_few_parts(self):
        """Test parsing invalid provider ID with too few parts."""
        with pytest.raises(TIMValidationError) as exc_info:
            parse_provider_id_with_version("hashicorp")
        assert "Invalid provider_id format" in str(exc_info.value)

    def test_parse_invalid_provider_id_too_many_parts(self):
        """Test parsing invalid provider ID with too many parts."""
        with pytest.raises(TIMValidationError) as exc_info:
            parse_provider_id_with_version("hashicorp/aws/5.70.0/extra")
        assert "Invalid provider_id format" in str(exc_info.value)

    def test_parse_empty_provider_id(self):
        """Test parsing empty provider ID."""
        with pytest.raises(TIMValidationError) as exc_info:
            parse_provider_id_with_version("")
        assert "Invalid provider_id format" in str(exc_info.value)


class TestFormatProviderDetails:
    """Test provider details formatting."""

    @pytest.fixture
    def sample_provider_data(self):
        """Sample provider data from API."""
        return {
            "id": "hashicorp/aws/6.14.1",
            "namespace": "hashicorp",
            "name": "aws",
            "version": "6.14.1",
            "description": "terraform-provider-aws",
            "source": "https://github.com/hashicorp/terraform-provider-aws",
            "downloads": 4966945606,
            "tier": "official",
            "published_at": "2025-09-22T17:13:05Z",
            "versions": ["6.14.1", "6.14.0", "6.13.0", "6.12.0", "6.11.0"],
        }

    def test_format_provider_details_success(self, sample_provider_data):
        """Test successful provider details formatting."""
        result = format_provider_details(sample_provider_data)

        # Verify key sections are present
        assert "hashicorp/aws - Provider Details" in result
        assert "v6.14.1" in result
        assert "Official" in result
        assert "4,966,945,606" in result  # Downloads with commas
        assert "terraform-provider-aws" in result
        assert "Available Versions" in result
        assert "Usage" in result
        assert "terraform {" in result  # HCL code block
        assert 'provider "aws"' in result

    def test_format_provider_details_missing_id(self):
        """Test formatting with missing provider ID."""
        data = {"namespace": "hashicorp", "name": "aws"}
        with pytest.raises(ValueError) as exc_info:
            format_provider_details(data)
        assert "required but missing" in str(exc_info.value)

    def test_format_provider_details_with_defaults(self):
        """Test formatting with default values for optional fields."""
        minimal_data = {
            "id": "test/provider/1.0.0",
            "namespace": "test",
            "name": "provider",
            "version": "1.0.0",
        }
        result = format_provider_details(minimal_data)

        # Should use default values
        assert "Community" in result  # Default tier
        assert "No description available" in result
        assert "0" in result  # Default downloads

    def test_format_version_list_many_versions(self):
        """Test version list formatting when there are many versions."""
        data = {
            "id": "hashicorp/aws/6.14.1",
            "namespace": "hashicorp",
            "name": "aws",
            "version": "6.14.1",
            "versions": [f"6.{i}.0" for i in range(20)],  # 20 versions
        }
        result = format_provider_details(data)

        # Should limit to latest 10 versions
        assert "showing latest 10 of 20 versions" in result


class TestGetProviderDetailsImpl:
    """Test the get_provider_details_impl function."""

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
    def sample_provider_response(self):
        """Sample response from Terraform Registry API."""
        return {
            "id": "hashicorp/aws/6.14.1",
            "namespace": "hashicorp",
            "name": "aws",
            "version": "6.14.1",
            "description": "terraform-provider-aws",
            "source": "https://github.com/hashicorp/terraform-provider-aws",
            "downloads": 4966945606,
            "tier": "official",
            "published_at": "2025-09-22T17:13:05Z",
            "versions": ["6.14.1", "6.14.0", "6.13.0"],
        }

    @pytest.mark.asyncio
    async def test_get_provider_details_without_version(
        self, config, mock_terraform_client, sample_provider_response
    ):
        """Test getting provider details without specifying version (latest)."""
        # Setup
        mock_terraform_client.get_provider_details.return_value = (
            sample_provider_response
        )
        request = ProviderDetailsRequest(provider_id="hashicorp/aws")

        with patch(
            "tim_mcp.tools.get_provider_details.TerraformClient"
        ) as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = (
                mock_terraform_client
            )

            # Execute
            result = await get_provider_details_impl(request, config)

            # Verify
            assert "hashicorp/aws - Provider Details" in result
            assert "v6.14.1" in result
            mock_terraform_client.get_provider_details.assert_called_once_with(
                namespace="hashicorp", name="aws", version="latest"
            )

    @pytest.mark.asyncio
    async def test_get_provider_details_with_version(
        self, config, mock_terraform_client, sample_provider_response
    ):
        """Test getting provider details with specific version."""
        # Setup - modify response for specific version
        specific_version_response = sample_provider_response.copy()
        specific_version_response["version"] = "5.70.0"
        specific_version_response["id"] = "hashicorp/aws/5.70.0"
        mock_terraform_client.get_provider_details.return_value = (
            specific_version_response
        )
        request = ProviderDetailsRequest(provider_id="hashicorp/aws/5.70.0")

        with patch(
            "tim_mcp.tools.get_provider_details.TerraformClient"
        ) as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = (
                mock_terraform_client
            )

            # Execute
            result = await get_provider_details_impl(request, config)

            # Verify
            assert "v5.70.0" in result
            mock_terraform_client.get_provider_details.assert_called_once_with(
                namespace="hashicorp", name="aws", version="5.70.0"
            )

    @pytest.mark.asyncio
    async def test_get_provider_details_invalid_provider_id(self, config):
        """Test getting provider details with invalid provider ID."""
        # Setup
        request = ProviderDetailsRequest(provider_id="invalid")

        with patch(
            "tim_mcp.tools.get_provider_details.TerraformClient"
        ) as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = AsyncMock()

            # Execute & Verify
            with pytest.raises(TerraformRegistryError) as exc_info:
                await get_provider_details_impl(request, config)

            assert "validation failed" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_get_provider_details_not_found(self, config, mock_terraform_client):
        """Test getting provider details for non-existent provider."""
        # Setup
        mock_terraform_client.get_provider_details.side_effect = TerraformRegistryError(
            "Not found", status_code=404
        )
        request = ProviderDetailsRequest(provider_id="nonexistent/provider")

        with patch(
            "tim_mcp.tools.get_provider_details.TerraformClient"
        ) as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = (
                mock_terraform_client
            )

            # Execute & Verify
            with pytest.raises(TerraformRegistryError) as exc_info:
                await get_provider_details_impl(request, config)

            assert exc_info.value.status_code == 404
            assert "not found" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_get_provider_details_api_error(self, config, mock_terraform_client):
        """Test getting provider details with API error."""
        # Setup
        mock_terraform_client.get_provider_details.side_effect = TerraformRegistryError(
            "Service unavailable", status_code=503
        )
        request = ProviderDetailsRequest(provider_id="hashicorp/aws")

        with patch(
            "tim_mcp.tools.get_provider_details.TerraformClient"
        ) as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = (
                mock_terraform_client
            )

            # Execute & Verify
            with pytest.raises(TerraformRegistryError) as exc_info:
                await get_provider_details_impl(request, config)

            assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_get_provider_details_malformed_response(
        self, config, mock_terraform_client
    ):
        """Test getting provider details with malformed API response."""
        # Setup - missing required fields
        malformed_response = {
            "namespace": "hashicorp",
            "name": "aws",
            # Missing id, version, etc.
        }
        mock_terraform_client.get_provider_details.return_value = malformed_response
        request = ProviderDetailsRequest(provider_id="hashicorp/aws")

        with patch(
            "tim_mcp.tools.get_provider_details.TerraformClient"
        ) as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = (
                mock_terraform_client
            )

            # Execute & Verify
            with pytest.raises(TerraformRegistryError) as exc_info:
                await get_provider_details_impl(request, config)

            assert "Invalid provider data" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_client_context_manager_usage(
        self, config, mock_terraform_client, sample_provider_response
    ):
        """Test that the TerraformClient is used as an async context manager."""
        # Setup
        mock_terraform_client.get_provider_details.return_value = (
            sample_provider_response
        )
        request = ProviderDetailsRequest(provider_id="hashicorp/aws")

        with patch(
            "tim_mcp.tools.get_provider_details.TerraformClient"
        ) as mock_client_class:
            # Set up the context manager correctly
            mock_instance = AsyncMock()
            mock_instance.__aenter__.return_value = mock_terraform_client
            mock_client_class.return_value = mock_instance

            # Execute
            await get_provider_details_impl(request, config)

            # Verify context manager methods were called
            mock_instance.__aenter__.assert_called_once()
            mock_instance.__aexit__.assert_called_once()


class TestProviderDetailsRequestValidation:
    """Test validation of ProviderDetailsRequest."""

    def test_valid_request_without_version(self):
        """Test valid request creation without version."""
        request = ProviderDetailsRequest(provider_id="hashicorp/aws")
        assert request.provider_id == "hashicorp/aws"

    def test_valid_request_with_version(self):
        """Test valid request creation with version."""
        request = ProviderDetailsRequest(provider_id="hashicorp/aws/5.70.0")
        assert request.provider_id == "hashicorp/aws/5.70.0"

    def test_empty_provider_id_validation(self):
        """Test empty provider ID validation."""
        with pytest.raises(ValidationError):
            ProviderDetailsRequest(provider_id="")
