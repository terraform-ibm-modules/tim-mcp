"""
Tests for the search_modules tool implementation.

Following TDD methodology - these tests define the behavior we want to implement.
"""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from tim_mcp.config import Config
from tim_mcp.exceptions import RateLimitError, TerraformRegistryError
from tim_mcp.exceptions import ValidationError as TIMValidationError
from tim_mcp.tools.search import search_modules_impl
from tim_mcp.types import ModuleInfo, ModuleSearchRequest, ModuleSearchResponse


class TestSearchModulesImpl:
    """Test the search_modules_impl function."""

    @pytest.fixture
    def config(self):
        """Create a test configuration."""
        return Config()

    @pytest.fixture
    def config_with_filtering(self):
        """Create a test configuration with filtering enabled."""
        return Config(
            allowed_namespaces=["terraform-ibm-modules", "ibm-garage-cloud"],
            excluded_modules=["terraform-ibm-modules/bad-module/ibm", "terraform-ibm-modules/deprecated-vpc/ibm"]
        )

    @pytest.fixture
    def mock_terraform_client(self):
        """Create a mock Terraform client."""
        client = AsyncMock()
        return client

    @pytest.fixture
    def sample_registry_response(self):
        """Sample response from Terraform Registry API."""
        return {
            "modules": [
                {
                    "id": "terraform-ibm-modules/vpc/ibm",
                    "namespace": "terraform-ibm-modules",
                    "name": "vpc",
                    "provider": "ibm",
                    "version": "5.1.0",
                    "description": "Provisions and configures IBM Cloud VPC resources",
                    "source": "https://github.com/terraform-ibm-modules/terraform-ibm-vpc",
                    "downloads": 53004,
                    "verified": False,
                    "published_at": "2025-09-02T08:33:15.000Z",
                },
                {
                    "id": "terraform-ibm-modules/security-group/ibm",
                    "namespace": "terraform-ibm-modules",
                    "name": "security-group",
                    "provider": "ibm",
                    "version": "2.3.1",
                    "description": "Creates and configures IBM Cloud security groups",
                    "source": "https://github.com/terraform-ibm-modules/terraform-ibm-security-group",
                    "downloads": 15234,
                    "verified": True,
                    "published_at": "2025-08-15T12:22:33.000Z",
                },
            ],
            "meta": {"limit": 10, "offset": 0, "total_count": 23},
        }

    @pytest.fixture
    def expected_response(self):
        """Expected formatted response."""
        return ModuleSearchResponse(
            query="vpc",
            total_found=23,
            modules=[
                ModuleInfo(
                    id="terraform-ibm-modules/vpc/ibm",
                    namespace="terraform-ibm-modules",
                    name="vpc",
                    provider="ibm",
                    version="5.1.0",
                    description="Provisions and configures IBM Cloud VPC resources",
                    source_url="https://github.com/terraform-ibm-modules/terraform-ibm-vpc",
                    downloads=53004,
                    verified=False,
                    published_at=datetime.fromisoformat("2025-09-02T08:33:15+00:00"),
                ),
                ModuleInfo(
                    id="terraform-ibm-modules/security-group/ibm",
                    namespace="terraform-ibm-modules",
                    name="security-group",
                    provider="ibm",
                    version="2.3.1",
                    description="Creates and configures IBM Cloud security groups",
                    source_url="https://github.com/terraform-ibm-modules/terraform-ibm-security-group",
                    downloads=15234,
                    verified=True,
                    published_at=datetime.fromisoformat("2025-08-15T12:22:33+00:00"),
                ),
            ],
        )

    @pytest.mark.asyncio
    async def test_successful_search_basic_query(
        self, config, mock_terraform_client, sample_registry_response, expected_response
    ):
        """Test successful module search with basic query."""
        # Setup
        mock_terraform_client.search_modules.return_value = sample_registry_response
        request = ModuleSearchRequest(query="vpc")

        with patch("tim_mcp.tools.search.TerraformClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_terraform_client
            # Execute
            result = await search_modules_impl(request, config)

            # Verify
            assert result == expected_response
            mock_terraform_client.search_modules.assert_called_once_with(
                query="vpc", namespace="terraform-ibm-modules", provider=None, limit=10, offset=0
            )

    @pytest.mark.asyncio
    async def test_successful_search_with_filters(self, config, mock_terraform_client, sample_registry_response):
        """Test successful module search with namespace and provider filters."""
        # Setup
        mock_terraform_client.search_modules.return_value = sample_registry_response
        request = ModuleSearchRequest(query="vpc", namespace="terraform-ibm-modules", provider="ibm", limit=5)

        with patch("tim_mcp.tools.search.TerraformClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_terraform_client
            # Execute
            result = await search_modules_impl(request, config)

            # Verify
            assert result.query == "vpc"
            assert result.total_found == 23
            assert len(result.modules) == 2
            mock_terraform_client.search_modules.assert_called_once_with(
                query="vpc",
                namespace="terraform-ibm-modules",
                provider="ibm",
                limit=5,
                offset=0,
            )

    @pytest.mark.asyncio
    async def test_empty_search_results(self, config, mock_terraform_client):
        """Test handling of empty search results."""
        # Setup
        empty_response = {
            "modules": [],
            "meta": {"limit": 10, "offset": 0, "total_count": 0},
        }
        mock_terraform_client.search_modules.return_value = empty_response
        request = ModuleSearchRequest(query="nonexistent")

        with patch("tim_mcp.tools.search.TerraformClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_terraform_client
            # Execute
            result = await search_modules_impl(request, config)

            # Verify
            assert result.query == "nonexistent"
            assert result.total_found == 0
            assert result.modules == []

    @pytest.mark.asyncio
    async def test_terraform_registry_error(self, config, mock_terraform_client):
        """Test handling of Terraform Registry API errors."""
        # Setup
        mock_terraform_client.search_modules.side_effect = TerraformRegistryError("API temporarily unavailable", status_code=503)
        request = ModuleSearchRequest(query="vpc")

        with patch("tim_mcp.tools.search.TerraformClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_terraform_client
            # Execute & Verify
            with pytest.raises(TerraformRegistryError) as exc_info:
                await search_modules_impl(request, config)

            assert "API temporarily unavailable" in str(exc_info.value)
            assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_rate_limit_error(self, config, mock_terraform_client):
        """Test handling of rate limit errors."""
        # Setup
        mock_terraform_client.search_modules.side_effect = RateLimitError(
            "Rate limit exceeded", reset_time=1695123456, api_name="Terraform Registry"
        )
        request = ModuleSearchRequest(query="vpc")

        with patch("tim_mcp.tools.search.TerraformClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_terraform_client
            # Execute & Verify
            with pytest.raises(RateLimitError) as exc_info:
                await search_modules_impl(request, config)

            assert "Rate limit exceeded" in str(exc_info.value)
            assert exc_info.value.reset_time == 1695123456

    @pytest.mark.asyncio
    async def test_malformed_api_response(self, config, mock_terraform_client):
        """Test handling of malformed API responses."""
        # Setup - missing required fields
        malformed_response = {
            "modules": [
                {
                    "id": "terraform-ibm-modules/vpc/ibm",
                    "namespace": "terraform-ibm-modules",
                    # Missing required fields like 'name', 'provider', etc.
                }
            ],
            "meta": {"limit": 10, "offset": 0, "total_count": 1},
        }
        mock_terraform_client.search_modules.return_value = malformed_response
        request = ModuleSearchRequest(query="vpc")

        with patch("tim_mcp.tools.search.TerraformClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_terraform_client
            # Execute & Verify
            with pytest.raises(TIMValidationError) as exc_info:
                await search_modules_impl(request, config)

            assert "Invalid module data" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_invalid_datetime_format(self, config, mock_terraform_client):
        """Test handling of invalid datetime formats in API response."""
        # Setup
        invalid_datetime_response = {
            "modules": [
                {
                    "id": "terraform-ibm-modules/vpc/ibm",
                    "namespace": "terraform-ibm-modules",
                    "name": "vpc",
                    "provider": "ibm",
                    "version": "5.1.0",
                    "description": "Test module",
                    "source": "https://github.com/terraform-ibm-modules/terraform-ibm-vpc",
                    "downloads": 123,
                    "verified": False,
                    "published_at": "invalid-date-format",
                }
            ],
            "meta": {"limit": 10, "offset": 0, "total_count": 1},
        }
        mock_terraform_client.search_modules.return_value = invalid_datetime_response
        request = ModuleSearchRequest(query="vpc")

        with patch("tim_mcp.tools.search.TerraformClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_terraform_client
            # Execute & Verify
            with pytest.raises(TIMValidationError) as exc_info:
                await search_modules_impl(request, config)

            assert "Invalid module data" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_missing_meta_information(self, config, mock_terraform_client):
        """Test handling of missing meta information in API response."""
        # Setup
        no_meta_response = {
            "modules": []
            # Missing 'meta' section
        }
        mock_terraform_client.search_modules.return_value = no_meta_response
        request = ModuleSearchRequest(query="vpc")

        with patch("tim_mcp.tools.search.TerraformClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_terraform_client
            # Execute & Verify
            with pytest.raises(TIMValidationError) as exc_info:
                await search_modules_impl(request, config)

            assert "Invalid API response format" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_client_context_manager_usage(self, config, mock_terraform_client, sample_registry_response):
        """Test that the TerraformClient is used as an async context manager."""
        # Setup
        mock_terraform_client.search_modules.return_value = sample_registry_response
        request = ModuleSearchRequest(query="vpc")

        with patch("tim_mcp.tools.search.TerraformClient") as mock_client_class:
            # Set up the context manager correctly
            mock_instance = AsyncMock()
            mock_instance.__aenter__.return_value = mock_terraform_client
            mock_client_class.return_value = mock_instance

            # Execute
            await search_modules_impl(request, config)

            # Verify context manager methods were called
            mock_instance.__aenter__.assert_called_once()
            mock_instance.__aexit__.assert_called_once()

    @pytest.mark.asyncio
    async def test_response_data_transformation(self, config, mock_terraform_client):
        """Test correct transformation of API response data to our format."""
        # Setup with specific test data
        api_response = {
            "modules": [
                {
                    "id": "test/module/provider",
                    "namespace": "test",
                    "name": "module",
                    "provider": "provider",
                    "version": "1.0.0",
                    "description": "Test description",
                    "source": "https://github.com/test/repo",
                    "downloads": 999,
                    "verified": True,
                    "published_at": "2025-01-01T12:00:00.000Z",
                }
            ],
            "meta": {"limit": 10, "offset": 0, "total_count": 1},
        }
        mock_terraform_client.search_modules.return_value = api_response
        request = ModuleSearchRequest(query="test")

        with patch("tim_mcp.tools.search.TerraformClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_terraform_client
            # Execute
            result = await search_modules_impl(request, config)

            # Verify transformation
            assert result.query == "test"
            assert result.total_found == 1
            assert len(result.modules) == 1

            module = result.modules[0]
            assert module.id == "test/module/provider"
            assert module.namespace == "test"
            assert module.name == "module"
            assert module.provider == "provider"
            assert module.version == "1.0.0"
            assert module.description == "Test description"
            assert str(module.source_url) == "https://github.com/test/repo"
            assert module.downloads == 999
            assert module.verified is True
            assert module.published_at == datetime.fromisoformat("2025-01-01T12:00:00+00:00")

    @pytest.mark.asyncio
    async def test_namespace_filtering_override_disallowed(
        self, config_with_filtering, mock_terraform_client, sample_registry_response
    ):
        """Test that disallowed namespaces are overridden with the first allowed namespace."""
        # Setup
        mock_terraform_client.search_modules.return_value = sample_registry_response
        # Request with disallowed namespace
        request = ModuleSearchRequest(query="vpc", namespace="some-disallowed-namespace")

        with patch("tim_mcp.tools.search.TerraformClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_terraform_client
            # Execute
            result = await search_modules_impl(request, config_with_filtering)

            # Verify that the search was called with the first allowed namespace instead
            mock_terraform_client.search_modules.assert_called_once_with(
                query="vpc",
                namespace="terraform-ibm-modules",  # First allowed namespace
                provider=None,
                limit=10,
                offset=0,
            )
            assert result.query == "vpc"

    @pytest.mark.asyncio
    async def test_namespace_filtering_allowed_namespace(
        self, config_with_filtering, mock_terraform_client, sample_registry_response
    ):
        """Test that allowed namespaces are passed through unchanged."""
        # Setup
        mock_terraform_client.search_modules.return_value = sample_registry_response
        # Request with allowed namespace
        request = ModuleSearchRequest(query="vpc", namespace="ibm-garage-cloud")

        with patch("tim_mcp.tools.search.TerraformClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_terraform_client
            # Execute
            result = await search_modules_impl(request, config_with_filtering)

            # Verify that the search was called with the requested namespace
            mock_terraform_client.search_modules.assert_called_once_with(
                query="vpc",
                namespace="ibm-garage-cloud",  # Requested namespace was allowed
                provider=None,
                limit=10,
                offset=0,
            )
            assert result.query == "vpc"

    @pytest.mark.asyncio
    async def test_namespace_filtering_default_when_none(
        self, config_with_filtering, mock_terraform_client, sample_registry_response
    ):
        """Test that the first allowed namespace is used when none is specified."""
        # Setup
        mock_terraform_client.search_modules.return_value = sample_registry_response
        # Request with no namespace
        request = ModuleSearchRequest(query="vpc")

        with patch("tim_mcp.tools.search.TerraformClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_terraform_client
            # Execute
            result = await search_modules_impl(request, config_with_filtering)

            # Verify that the search was called with the first allowed namespace
            mock_terraform_client.search_modules.assert_called_once_with(
                query="vpc",
                namespace="terraform-ibm-modules",  # First allowed namespace
                provider=None,
                limit=10,
                offset=0,
            )
            assert result.query == "vpc"

    @pytest.mark.asyncio
    async def test_module_exclusion_filtering(self, config_with_filtering, mock_terraform_client):
        """Test that excluded modules are filtered out from results."""
        # Setup - response with both allowed and excluded modules
        response_with_excluded = {
            "modules": [
                {
                    "id": "terraform-ibm-modules/vpc/ibm",
                    "namespace": "terraform-ibm-modules",
                    "name": "vpc",
                    "provider": "ibm",
                    "version": "5.1.0",
                    "description": "Provisions and configures IBM Cloud VPC resources",
                    "source": "https://github.com/terraform-ibm-modules/terraform-ibm-vpc",
                    "downloads": 53004,
                    "verified": False,
                    "published_at": "2025-09-02T08:33:15.000Z",
                },
                {
                    "id": "terraform-ibm-modules/bad-module/ibm",  # This should be excluded
                    "namespace": "terraform-ibm-modules",
                    "name": "bad-module",
                    "provider": "ibm",
                    "version": "1.0.0",
                    "description": "This module has issues",
                    "source": "https://github.com/terraform-ibm-modules/terraform-ibm-bad-module",
                    "downloads": 10,
                    "verified": False,
                    "published_at": "2025-08-01T10:00:00.000Z",
                },
                {
                    "id": "terraform-ibm-modules/security-group/ibm",
                    "namespace": "terraform-ibm-modules",
                    "name": "security-group",
                    "provider": "ibm",
                    "version": "2.3.1",
                    "description": "Creates and configures IBM Cloud security groups",
                    "source": "https://github.com/terraform-ibm-modules/terraform-ibm-security-group",
                    "downloads": 15234,
                    "verified": True,
                    "published_at": "2025-08-15T12:22:33.000Z",
                },
            ],
            "meta": {"limit": 10, "offset": 0, "total_count": 3},
        }

        mock_terraform_client.search_modules.return_value = response_with_excluded
        request = ModuleSearchRequest(query="modules")

        with patch("tim_mcp.tools.search.TerraformClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_terraform_client
            # Execute
            result = await search_modules_impl(request, config_with_filtering)

            # Verify that only non-excluded modules are in the results
            assert result.query == "modules"
            assert result.total_found == 3  # Original total from API
            assert len(result.modules) == 2  # One module was excluded

            # Verify the excluded module is not in results
            module_ids = [module.id for module in result.modules]
            assert "terraform-ibm-modules/vpc/ibm" in module_ids
            assert "terraform-ibm-modules/security-group/ibm" in module_ids
            assert "terraform-ibm-modules/bad-module/ibm" not in module_ids  # Excluded

    @pytest.mark.asyncio
    async def test_empty_allowed_namespaces_no_filtering(self, mock_terraform_client, sample_registry_response):
        """Test behavior when allowed_namespaces is empty - no filtering should occur."""
        # Setup config with empty allowed namespaces
        config_no_filtering = Config(allowed_namespaces=[], excluded_modules=[])
        mock_terraform_client.search_modules.return_value = sample_registry_response
        request = ModuleSearchRequest(query="vpc", namespace="any-namespace")

        with patch("tim_mcp.tools.search.TerraformClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_terraform_client
            # Execute
            result = await search_modules_impl(request, config_no_filtering)

            # Verify that the original namespace was passed through
            mock_terraform_client.search_modules.assert_called_once_with(
                query="vpc",
                namespace="any-namespace",  # Original namespace preserved
                provider=None,
                limit=10,
                offset=0,
            )
            assert result.query == "vpc"


class TestModuleSearchRequestValidation:
    """Test validation of ModuleSearchRequest."""

    def test_valid_request(self):
        """Test valid request creation."""
        request = ModuleSearchRequest(query="vpc", namespace="terraform-ibm-modules", provider="ibm", limit=5)
        assert request.query == "vpc"
        assert request.namespace == "terraform-ibm-modules"
        assert request.provider == "ibm"
        assert request.limit == 5

    def test_default_limit(self):
        """Test default limit is applied."""
        request = ModuleSearchRequest(query="vpc")
        assert request.limit == 10

    def test_limit_validation_min(self):
        """Test limit minimum validation."""
        with pytest.raises(ValidationError):
            ModuleSearchRequest(query="vpc", limit=0)

    def test_limit_validation_max(self):
        """Test limit maximum validation."""
        with pytest.raises(ValidationError):
            ModuleSearchRequest(query="vpc", limit=101)

    def test_empty_query_validation(self):
        """Test empty query validation."""
        with pytest.raises(ValidationError):
            ModuleSearchRequest(query="")

    def test_optional_fields_none(self):
        """Test optional fields can be None."""
        request = ModuleSearchRequest(query="vpc", namespace=None, provider=None)
        assert request.namespace is None
        assert request.provider is None


class TestModuleInfoValidation:
    """Test validation of ModuleInfo model."""

    def test_valid_module_info(self):
        """Test valid ModuleInfo creation."""
        module = ModuleInfo(
            id="test/module/provider",
            namespace="test",
            name="module",
            provider="provider",
            version="1.0.0",
            description="Test description",
            source_url="https://github.com/test/repo",
            downloads=100,
            verified=True,
            published_at=datetime.now(),
        )
        assert module.id == "test/module/provider"
        assert module.downloads == 100

    def test_invalid_source_url(self):
        """Test invalid source URL validation."""
        with pytest.raises(ValidationError):
            ModuleInfo(
                id="test/module/provider",
                namespace="test",
                name="module",
                provider="provider",
                version="1.0.0",
                description="Test description",
                source_url="not-a-url",
                downloads=100,
                verified=True,
                published_at=datetime.now(),
            )

    def test_negative_downloads(self):
        """Test negative downloads validation."""
        with pytest.raises(ValidationError):
            ModuleInfo(
                id="test/module/provider",
                namespace="test",
                name="module",
                provider="provider",
                version="1.0.0",
                description="Test description",
                source_url="https://github.com/test/repo",
                downloads=-1,
                verified=True,
                published_at=datetime.now(),
            )
