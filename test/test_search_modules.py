"""
Tests for the search_modules tool implementation.

Following TDD methodology - these tests define the behavior we want to implement.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from tim_mcp.config import Config
from tim_mcp.exceptions import RateLimitError, TerraformRegistryError
from tim_mcp.exceptions import ValidationError as TIMValidationError
from tim_mcp.tools.search import search_modules_impl
from tim_mcp.types import ModuleInfo, ModuleSearchRequest, ModuleSearchResponse


class TestSearchModulesImpl:
    """Test the search_modules_impl function."""

    def _create_mock_github_client(self):
        """Create a properly configured mock GitHub client."""
        mock_github_client = AsyncMock()
        mock_github_client.parse_github_url.side_effect = lambda url: (
            ("terraform-ibm-modules", "terraform-ibm-vpc")
            if "vpc" in url
            else ("terraform-ibm-modules", "terraform-ibm-security-group")
            if "security-group" in url
            else None
        )

        # Mock async function to return the expected dict with topics
        async def mock_get_repo_info(*args, **kwargs):
            return {
                "default_branch": "main",
                "size": 100,
                "archived": False,
                "topics": [
                    "terraform",
                    "ibm-cloud",
                    "terraform-module",
                ],  # Add required topics
            }

        mock_github_client.get_repository_info = mock_get_repo_info
        return mock_github_client

    @pytest.fixture
    def config(self):
        """Create a test configuration."""
        return Config()

    @pytest.fixture
    def config_with_filtering(self):
        """Create a test configuration with filtering enabled."""
        return Config(
            allowed_namespaces=["terraform-ibm-modules", "ibm-garage-cloud"],
            excluded_modules=[
                "terraform-ibm-modules/bad-module/ibm",
                "terraform-ibm-modules/deprecated-vpc/ibm",
            ],
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
        # Setup - provide responses for counting phase and validation phase
        mock_terraform_client.search_modules.side_effect = [
            sample_registry_response,  # Counting phase: counts 2, no next_offset, stops
            sample_registry_response,  # Validation phase: gets 2, hits limit of 2, stops
        ]
        request = ModuleSearchRequest(
            query="vpc", limit=2
        )  # Request only 2 to match available

        # Create a mock GitHub client
        mock_github_client = self._create_mock_github_client()

        with (
            patch("tim_mcp.tools.search.TerraformClient") as mock_tf_class,
            patch("tim_mcp.tools.search.GitHubClient") as mock_gh_class,
            patch("tim_mcp.tools.search._is_repository_valid") as mock_is_valid,
        ):
            mock_tf_class.return_value.__aenter__.return_value = mock_terraform_client
            mock_gh_class.return_value.__aenter__.return_value = mock_github_client
            # Always return True for repository validation
            mock_is_valid.return_value = True

            # Execute
            result = await search_modules_impl(request, config)

            # Verify
            assert result.query == expected_response.query
            assert result.total_found == 2  # Counted 2 modules total
            assert len(result.modules) == 2  # Got 2 modules as requested
            assert result.modules == expected_response.modules
            # Check that search was called 2 times (1 for counting, 1 for validation)
            assert mock_terraform_client.search_modules.call_count == 2

    @pytest.mark.asyncio
    async def test_successful_search_with_limit(
        self, config, mock_terraform_client, sample_registry_response
    ):
        """Test successful module search with custom limit."""
        # Setup - return modules in batches for counting then validation
        # Need to add next_offset to meta to enable pagination
        response_with_next = {
            **sample_registry_response,
            "meta": {**sample_registry_response["meta"], "next_offset": 2},
        }
        mock_terraform_client.search_modules.side_effect = [
            # Counting phase (limit=100) - count all 6 modules across 3 batches
            response_with_next,  # First batch (2 modules), has next_offset
            response_with_next,  # Second batch (2 modules), has next_offset
            sample_registry_response,  # Third batch (2 modules), no next_offset, stops
            # Validation phase (limit=50) - get 5 modules (3 batches)
            response_with_next,  # First batch (2 modules), has next_offset
            response_with_next,  # Second batch (2 modules), has next_offset
            sample_registry_response,  # Third batch (2 modules), no next_offset, stops at 6
        ]
        request = ModuleSearchRequest(query="vpc", limit=5)

        # Create a mock GitHub client
        mock_github_client = self._create_mock_github_client()

        with (
            patch("tim_mcp.tools.search.TerraformClient") as mock_tf_class,
            patch("tim_mcp.tools.search.GitHubClient") as mock_gh_class,
            patch("tim_mcp.tools.search._is_repository_valid") as mock_is_valid,
        ):
            mock_tf_class.return_value.__aenter__.return_value = mock_terraform_client
            mock_gh_class.return_value.__aenter__.return_value = mock_github_client
            # Always return True for repository validation
            mock_is_valid.return_value = True
            # Execute
            result = await search_modules_impl(request, config)

            # Verify
            assert result.query == "vpc"
            assert result.total_found == 6  # Counted 6 modules (3 batches * 2)
            assert len(result.modules) == 5  # Should get 5 modules as requested

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

        # Create a mock GitHub client
        mock_github_client = self._create_mock_github_client()

        with (
            patch("tim_mcp.tools.search.TerraformClient") as mock_tf_class,
            patch("tim_mcp.tools.search.GitHubClient") as mock_gh_class,
            patch("tim_mcp.tools.search._is_repository_valid") as mock_is_valid,
        ):
            mock_tf_class.return_value.__aenter__.return_value = mock_terraform_client
            mock_gh_class.return_value.__aenter__.return_value = mock_github_client
            # Always return True for repository validation
            mock_is_valid.return_value = True
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
        mock_terraform_client.search_modules.side_effect = TerraformRegistryError(
            "API temporarily unavailable", status_code=503
        )
        request = ModuleSearchRequest(query="vpc")

        with patch("tim_mcp.tools.search.TerraformClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = (
                mock_terraform_client
            )
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
            mock_client_class.return_value.__aenter__.return_value = (
                mock_terraform_client
            )
            # Execute & Verify
            with pytest.raises(RateLimitError) as exc_info:
                await search_modules_impl(request, config)

            assert "Rate limit exceeded" in str(exc_info.value)
            assert exc_info.value.reset_time == 1695123456

    @pytest.mark.asyncio
    async def test_malformed_api_response(self, config, mock_terraform_client):
        """Test handling of malformed API responses - invalid modules are skipped."""
        # Setup - all modules have missing required fields
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
        mock_terraform_client.search_modules.side_effect = [
            malformed_response,
            {"modules": [], "meta": {"limit": 50, "offset": 50, "total_count": 1}},
        ]
        request = ModuleSearchRequest(query="vpc")

        mock_github_client = AsyncMock()
        with (
            patch("tim_mcp.tools.search.TerraformClient") as mock_tf_class,
            patch("tim_mcp.tools.search.GitHubClient") as mock_gh_class,
            patch("tim_mcp.tools.search._is_repository_valid") as mock_is_valid,
        ):
            mock_tf_class.return_value.__aenter__.return_value = mock_terraform_client
            mock_gh_class.return_value.__aenter__.return_value = mock_github_client
            mock_is_valid.return_value = True

            # Execute - should handle malformed data gracefully
            result = await search_modules_impl(request, config)

            # Verify - no modules should be in results since all were invalid
            assert len(result.modules) == 0
            assert result.total_found == 1

    @pytest.mark.asyncio
    async def test_invalid_datetime_format(self, config, mock_terraform_client):
        """Test handling of invalid datetime formats - modules with bad dates are skipped."""
        # Setup
        invalid_datetime_response = {
            "modules": [
                {
                    "id": "terraform-ibm-modules/bad-date/ibm",
                    "namespace": "terraform-ibm-modules",
                    "name": "bad-date",
                    "provider": "ibm",
                    "version": "5.1.0",
                    "description": "Test module",
                    "source": "https://github.com/terraform-ibm-modules/terraform-ibm-vpc",
                    "downloads": 123,
                    "verified": False,
                    "published_at": "invalid-date-format",
                },
                {  # Valid module
                    "id": "terraform-ibm-modules/vpc/ibm",
                    "namespace": "terraform-ibm-modules",
                    "name": "vpc",
                    "provider": "ibm",
                    "version": "1.0.0",
                    "description": "Valid module",
                    "source": "https://github.com/terraform-ibm-modules/terraform-ibm-vpc",
                    "downloads": 100,
                    "verified": False,
                    "published_at": "2025-01-01T00:00:00.000Z",
                },
            ],
            "meta": {"limit": 10, "offset": 0, "total_count": 2},
        }
        mock_terraform_client.search_modules.side_effect = [
            invalid_datetime_response,  # Counting phase
            invalid_datetime_response,  # Validation phase
        ]
        request = ModuleSearchRequest(
            query="vpc", limit=1
        )  # Only 1 valid module available

        mock_github_client = self._create_mock_github_client()

        with (
            patch("tim_mcp.tools.search.TerraformClient") as mock_tf_class,
            patch("tim_mcp.tools.search.GitHubClient") as mock_gh_class,
            patch("tim_mcp.tools.search._is_repository_valid") as mock_is_valid,
        ):
            mock_tf_class.return_value.__aenter__.return_value = mock_terraform_client
            mock_gh_class.return_value.__aenter__.return_value = mock_github_client
            mock_is_valid.return_value = True

            # Execute - should handle invalid datetime gracefully
            result = await search_modules_impl(request, config)

            # Verify - only the valid module should be in results
            assert len(result.modules) == 1
            assert result.modules[0].id == "terraform-ibm-modules/vpc/ibm"

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
            mock_client_class.return_value.__aenter__.return_value = (
                mock_terraform_client
            )
            # Execute & Verify
            with pytest.raises(TIMValidationError) as exc_info:
                await search_modules_impl(request, config)

            assert "Invalid API response format" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_client_context_manager_usage(
        self, config, mock_terraform_client, sample_registry_response
    ):
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
        mock_terraform_client.search_modules.side_effect = [
            api_response,  # Counting phase
            api_response,  # Validation phase
        ]
        request = ModuleSearchRequest(query="test", limit=1)  # Only 1 module available

        mock_github_client = AsyncMock()
        with (
            patch("tim_mcp.tools.search.TerraformClient") as mock_tf_class,
            patch("tim_mcp.tools.search.GitHubClient") as mock_gh_class,
            patch("tim_mcp.tools.search._is_repository_valid") as mock_is_valid,
        ):
            mock_tf_class.return_value.__aenter__.return_value = mock_terraform_client
            mock_gh_class.return_value.__aenter__.return_value = mock_github_client
            mock_is_valid.return_value = True

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
            assert module.published_at == datetime.fromisoformat(
                "2025-01-01T12:00:00+00:00"
            )

    @pytest.mark.asyncio
    async def test_namespace_filtering_uses_configured(
        self, config_with_filtering, mock_terraform_client, sample_registry_response
    ):
        """Test that the configured namespace is used from config."""
        # Setup
        mock_terraform_client.search_modules.side_effect = [
            sample_registry_response,
            {"modules": [], "meta": {"limit": 50, "offset": 50, "total_count": 23}},
        ]
        # Request without namespace parameter
        request = ModuleSearchRequest(query="vpc")

        mock_github_client = AsyncMock()
        with (
            patch("tim_mcp.tools.search.TerraformClient") as mock_tf_class,
            patch("tim_mcp.tools.search.GitHubClient") as mock_gh_class,
            patch("tim_mcp.tools.search._is_repository_valid") as mock_is_valid,
        ):
            mock_tf_class.return_value.__aenter__.return_value = mock_terraform_client
            mock_gh_class.return_value.__aenter__.return_value = mock_github_client
            mock_is_valid.return_value = True
            # Execute
            result = await search_modules_impl(request, config_with_filtering)

            # Verify that the search was called with the first allowed namespace
            mock_terraform_client.search_modules.assert_any_call(
                query="vpc",
                namespace="terraform-ibm-modules",  # First allowed namespace from config
                limit=50,  # batch_size is 50
                offset=0,
            )
            assert result.query == "vpc"

    @pytest.mark.asyncio
    async def test_module_exclusion_filtering(
        self, config_with_filtering, mock_terraform_client
    ):
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

        # Need to provide multiple batches to get 5 valid modules (excluding bad-module)
        response_with_next = {
            **response_with_excluded,
            "meta": {**response_with_excluded["meta"], "next_offset": 3},
        }
        mock_terraform_client.search_modules.side_effect = [
            response_with_excluded,  # Counting phase: 3 modules total
            # Validation phase: need multiple batches to get 5 valid (2 valid per batch)
            response_with_next,  # First batch: 2 valid
            response_with_next,  # Second batch: 2 valid
            response_with_excluded,  # Third batch: 2 valid, total 6, stops at 5
        ]
        request = ModuleSearchRequest(query="modules")

        mock_github_client = AsyncMock()
        with (
            patch("tim_mcp.tools.search.TerraformClient") as mock_tf_class,
            patch("tim_mcp.tools.search.GitHubClient") as mock_gh_class,
            patch("tim_mcp.tools.search._is_repository_valid") as mock_is_valid,
        ):
            mock_tf_class.return_value.__aenter__.return_value = mock_terraform_client
            mock_gh_class.return_value.__aenter__.return_value = mock_github_client
            mock_is_valid.return_value = True

            # Execute
            result = await search_modules_impl(request, config_with_filtering)

            # Verify that only non-excluded modules are in the results
            assert result.query == "modules"
            assert result.total_found == 3  # Original total from API
            assert len(result.modules) == 5  # Should reach limit of 5 (default)

            # Verify the excluded module is not in results
            module_ids = [module.id for module in result.modules]
            assert "terraform-ibm-modules/vpc/ibm" in module_ids
            assert "terraform-ibm-modules/security-group/ibm" in module_ids
            assert "terraform-ibm-modules/bad-module/ibm" not in module_ids  # Excluded

    @pytest.mark.asyncio
    async def test_empty_allowed_namespaces_no_filtering(
        self, mock_terraform_client, sample_registry_response
    ):
        """Test behavior when allowed_namespaces is empty - no namespace filtering should occur."""
        # Setup config with empty allowed namespaces
        config_no_filtering = Config(allowed_namespaces=[], excluded_modules=[])
        mock_terraform_client.search_modules.side_effect = [
            sample_registry_response,
            {"modules": [], "meta": {"limit": 50, "offset": 50, "total_count": 23}},
        ]
        request = ModuleSearchRequest(query="vpc")

        mock_github_client = AsyncMock()
        with (
            patch("tim_mcp.tools.search.TerraformClient") as mock_tf_class,
            patch("tim_mcp.tools.search.GitHubClient") as mock_gh_class,
            patch("tim_mcp.tools.search._is_repository_valid") as mock_is_valid,
        ):
            mock_tf_class.return_value.__aenter__.return_value = mock_terraform_client
            mock_gh_class.return_value.__aenter__.return_value = mock_github_client
            mock_is_valid.return_value = True
            # Execute
            result = await search_modules_impl(request, config_no_filtering)

            # Verify that None namespace was passed (no filtering)
            mock_terraform_client.search_modules.assert_any_call(
                query="vpc",
                namespace=None,  # No namespace filtering when config is empty
                limit=50,  # batch_size is 50
                offset=0,
            )
            assert result.query == "vpc"

    @pytest.mark.asyncio
    async def test_download_sorting(self, config, mock_terraform_client):
        """Test that results are sorted by downloads in descending order."""
        # Setup - response with modules in wrong download order
        unsorted_response = {
            "modules": [
                {
                    "id": "terraform-ibm-modules/low-downloads/ibm",
                    "namespace": "terraform-ibm-modules",
                    "name": "low-downloads",
                    "provider": "ibm",
                    "version": "1.0.0",
                    "description": "Module with few downloads",
                    "source": "https://github.com/terraform-ibm-modules/low-downloads",
                    "downloads": 100,  # Low downloads
                    "verified": False,
                    "published_at": "2025-09-01T08:00:00.000Z",
                },
                {
                    "id": "terraform-ibm-modules/high-downloads/ibm",
                    "namespace": "terraform-ibm-modules",
                    "name": "high-downloads",
                    "provider": "ibm",
                    "version": "2.0.0",
                    "description": "Module with many downloads",
                    "source": "https://github.com/terraform-ibm-modules/high-downloads",
                    "downloads": 50000,  # High downloads
                    "verified": True,
                    "published_at": "2025-09-02T08:00:00.000Z",
                },
                {
                    "id": "terraform-ibm-modules/medium-downloads/ibm",
                    "namespace": "terraform-ibm-modules",
                    "name": "medium-downloads",
                    "provider": "ibm",
                    "version": "1.5.0",
                    "description": "Module with medium downloads",
                    "source": "https://github.com/terraform-ibm-modules/medium-downloads",
                    "downloads": 5000,  # Medium downloads
                    "verified": False,
                    "published_at": "2025-09-01T12:00:00.000Z",
                },
            ],
            "meta": {"limit": 100, "offset": 0, "total_count": 3},
        }

        mock_terraform_client.search_modules.side_effect = [
            unsorted_response,  # Counting phase
            unsorted_response,  # Validation phase
        ]
        request = ModuleSearchRequest(query="modules", limit=3)  # 3 modules available

        mock_github_client = AsyncMock()
        with (
            patch("tim_mcp.tools.search.TerraformClient") as mock_tf_class,
            patch("tim_mcp.tools.search.GitHubClient") as mock_gh_class,
            patch("tim_mcp.tools.search._is_repository_valid") as mock_is_valid,
        ):
            mock_tf_class.return_value.__aenter__.return_value = mock_terraform_client
            mock_gh_class.return_value.__aenter__.return_value = mock_github_client
            mock_is_valid.return_value = True

            # Execute
            result = await search_modules_impl(request, config)

            # Verify that results are sorted by downloads descending
            assert result.query == "modules"
            assert result.total_found == 3
            assert len(result.modules) == 3

            # Check order: high (50000) -> medium (5000) -> low (100)
            assert result.modules[0].downloads == 50000
            assert result.modules[0].id == "terraform-ibm-modules/high-downloads/ibm"
            assert result.modules[1].downloads == 5000
            assert result.modules[1].id == "terraform-ibm-modules/medium-downloads/ibm"
            assert result.modules[2].downloads == 100
            assert result.modules[2].id == "terraform-ibm-modules/low-downloads/ibm"

    @pytest.mark.asyncio
    async def test_download_sorting_with_limit(self, config, mock_terraform_client):
        """Test that sorting works correctly when applying user's limit."""
        # Setup - same unsorted response as above
        unsorted_response = {
            "modules": [
                {
                    "id": "terraform-ibm-modules/low-downloads/ibm",
                    "namespace": "terraform-ibm-modules",
                    "name": "low-downloads",
                    "provider": "ibm",
                    "version": "1.0.0",
                    "description": "Module with few downloads",
                    "source": "https://github.com/terraform-ibm-modules/low-downloads",
                    "downloads": 100,
                    "verified": False,
                    "published_at": "2025-09-01T08:00:00.000Z",
                },
                {
                    "id": "terraform-ibm-modules/high-downloads/ibm",
                    "namespace": "terraform-ibm-modules",
                    "name": "high-downloads",
                    "provider": "ibm",
                    "version": "2.0.0",
                    "description": "Module with many downloads",
                    "source": "https://github.com/terraform-ibm-modules/high-downloads",
                    "downloads": 50000,
                    "verified": True,
                    "published_at": "2025-09-02T08:00:00.000Z",
                },
                {
                    "id": "terraform-ibm-modules/medium-downloads/ibm",
                    "namespace": "terraform-ibm-modules",
                    "name": "medium-downloads",
                    "provider": "ibm",
                    "version": "1.5.0",
                    "description": "Module with medium downloads",
                    "source": "https://github.com/terraform-ibm-modules/medium-downloads",
                    "downloads": 5000,
                    "verified": False,
                    "published_at": "2025-09-01T12:00:00.000Z",
                },
            ],
            "meta": {"limit": 100, "offset": 0, "total_count": 3},
        }

        mock_terraform_client.search_modules.side_effect = [
            unsorted_response,  # Counting phase
            unsorted_response,  # Validation phase
        ]
        # Request only top 2 results
        request = ModuleSearchRequest(query="modules", limit=2)

        mock_github_client = AsyncMock()
        with (
            patch("tim_mcp.tools.search.TerraformClient") as mock_tf_class,
            patch("tim_mcp.tools.search.GitHubClient") as mock_gh_class,
            patch("tim_mcp.tools.search._is_repository_valid") as mock_is_valid,
        ):
            mock_tf_class.return_value.__aenter__.return_value = mock_terraform_client
            mock_gh_class.return_value.__aenter__.return_value = mock_github_client
            mock_is_valid.return_value = True

            # Execute
            result = await search_modules_impl(request, config)

            # Verify that we get top 2 by downloads
            assert result.query == "modules"
            assert result.total_found == 3
            assert len(result.modules) == 2  # Limited to 2

            # Check that we got the top 2: high (50000) and medium (5000)
            assert result.modules[0].downloads == 50000
            assert result.modules[0].id == "terraform-ibm-modules/high-downloads/ibm"
            assert result.modules[1].downloads == 5000
            assert result.modules[1].id == "terraform-ibm-modules/medium-downloads/ibm"

    @pytest.mark.asyncio
    async def test_download_sorting_same_counts(self, config, mock_terraform_client):
        """Test sorting behavior when modules have the same download counts."""
        # Setup - modules with same download counts
        same_downloads_response = {
            "modules": [
                {
                    "id": "terraform-ibm-modules/module-a/ibm",
                    "namespace": "terraform-ibm-modules",
                    "name": "module-a",
                    "provider": "ibm",
                    "version": "1.0.0",
                    "description": "Module A",
                    "source": "https://github.com/terraform-ibm-modules/module-a",
                    "downloads": 1000,  # Same downloads
                    "verified": False,
                    "published_at": "2025-09-01T08:00:00.000Z",
                },
                {
                    "id": "terraform-ibm-modules/module-b/ibm",
                    "namespace": "terraform-ibm-modules",
                    "name": "module-b",
                    "provider": "ibm",
                    "version": "1.0.0",
                    "description": "Module B",
                    "source": "https://github.com/terraform-ibm-modules/module-b",
                    "downloads": 1000,  # Same downloads
                    "verified": False,
                    "published_at": "2025-09-02T08:00:00.000Z",
                },
            ],
            "meta": {"limit": 100, "offset": 0, "total_count": 2},
        }

        mock_terraform_client.search_modules.side_effect = [
            same_downloads_response,  # Counting phase
            same_downloads_response,  # Validation phase
        ]
        request = ModuleSearchRequest(query="modules", limit=2)  # 2 modules available

        mock_github_client = AsyncMock()
        with (
            patch("tim_mcp.tools.search.TerraformClient") as mock_tf_class,
            patch("tim_mcp.tools.search.GitHubClient") as mock_gh_class,
            patch("tim_mcp.tools.search._is_repository_valid") as mock_is_valid,
        ):
            mock_tf_class.return_value.__aenter__.return_value = mock_terraform_client
            mock_gh_class.return_value.__aenter__.return_value = mock_github_client
            mock_is_valid.return_value = True

            # Execute
            result = await search_modules_impl(request, config)

            # Verify that results are returned (order may be stable but not guaranteed)
            assert result.query == "modules"
            assert result.total_found == 2
            assert len(result.modules) == 2
            # Both modules should have same download count
            assert all(module.downloads == 1000 for module in result.modules)

    @pytest.mark.asyncio
    async def test_pre_release_version_resolution(self, mock_terraform_client, config):
        """Test that pre-release versions are resolved to latest stable version."""
        # Setup - API returns module with pre-release version
        prerelease_response = {
            "modules": [
                {
                    "id": "terraform-ibm-modules/db2-cloud/ibm",
                    "namespace": "terraform-ibm-modules",
                    "name": "db2-cloud",
                    "provider": "ibm",
                    "version": "2.0.1-draft-addons",  # Pre-release
                    "description": "Provision a fully managed database",
                    "source": "https://github.com/terraform-ibm-modules/terraform-ibm-db2-cloud",
                    "downloads": 133,
                    "verified": False,
                    "published_at": "2025-06-13T14:26:41.000Z",
                }
            ],
            "meta": {"limit": 100, "offset": 0, "total_count": 1},
        }

        # Mock to return stable versions in chronological order
        mock_terraform_client.search_modules.side_effect = [
            prerelease_response,  # Counting phase
            prerelease_response,  # Validation phase
        ]
        # Versions in chronological order (oldest first, as returned by API)
        mock_terraform_client.get_module_versions.return_value = [
            "1.9.0",
            "2.0.0",
            "2.0.1-draft-addons",
        ]
        # Mock get_module_details to return complete module data for stable version
        mock_terraform_client.get_module_details.return_value = {
            "id": "terraform-ibm-modules/db2-cloud/ibm/2.0.0",
            "namespace": "terraform-ibm-modules",
            "name": "db2-cloud",
            "provider": "ibm",
            "version": "2.0.0",
            "description": "Provision a fully managed database (stable version)",
            "source": "https://github.com/terraform-ibm-modules/terraform-ibm-db2-cloud",
            "downloads": 150,
            "verified": False,
            "published_at": "2025-05-01T10:00:00.000Z",
        }

        request = ModuleSearchRequest(query="database", limit=1)  # 1 module available

        with (
            patch("tim_mcp.tools.search.TerraformClient") as mock_tf_class,
            patch("tim_mcp.tools.search.GitHubClient") as mock_gh_class,
            patch("tim_mcp.tools.search._is_repository_valid") as mock_is_valid,
        ):
            mock_tf_class.return_value.__aenter__.return_value = mock_terraform_client
            mock_gh_class.return_value.__aenter__.return_value = AsyncMock()
            mock_is_valid.return_value = True

            # Execute
            result = await search_modules_impl(request, config)

            # Verify - complete module details fetched for latest stable version
            assert len(result.modules) == 1
            assert result.modules[0].version == "2.0.0"  # Latest stable
            assert (
                result.modules[0].description
                == "Provision a fully managed database (stable version)"
            )
            assert result.modules[0].downloads == 150  # From stable version details
            mock_terraform_client.get_module_versions.assert_called_once_with(
                namespace="terraform-ibm-modules",
                name="db2-cloud",
                provider="ibm",
            )
            mock_terraform_client.get_module_details.assert_called_once_with(
                namespace="terraform-ibm-modules",
                name="db2-cloud",
                provider="ibm",
                version="2.0.0",
            )

    @pytest.mark.asyncio
    async def test_module_with_only_prerelease_versions_excluded(
        self, mock_terraform_client, config
    ):
        """Test that modules with only pre-release versions are excluded."""
        # Setup - API returns module with pre-release version
        prerelease_response = {
            "modules": [
                {
                    "id": "terraform-ibm-modules/test-module/ibm",
                    "namespace": "terraform-ibm-modules",
                    "name": "test-module",
                    "provider": "ibm",
                    "version": "1.0.0-beta1",  # Pre-release
                    "description": "Test module",
                    "source": "https://github.com/terraform-ibm-modules/test-module",
                    "downloads": 10,
                    "verified": False,
                    "published_at": "2025-01-01T00:00:00.000Z",
                }
            ],
            "meta": {"limit": 100, "offset": 0, "total_count": 1},
        }

        # Mock get_module_versions to return only pre-release versions
        mock_terraform_client.search_modules.side_effect = [
            prerelease_response,  # Counting phase
            prerelease_response,  # Validation phase batch 1: module gets filtered out (no stable versions)
            {"modules": [], "meta": {}},  # Validation phase batch 2: no more modules
        ]
        mock_terraform_client.get_module_versions.return_value = [
            "1.0.0-beta1",
            "1.0.0-alpha",
        ]

        request = ModuleSearchRequest(
            query="test", limit=1
        )  # Expect 0 modules (all pre-release filtered out)

        with (
            patch("tim_mcp.tools.search.TerraformClient") as mock_tf_class,
            patch("tim_mcp.tools.search.GitHubClient") as mock_gh_class,
        ):
            mock_tf_class.return_value.__aenter__.return_value = mock_terraform_client
            mock_gh_class.return_value.__aenter__.return_value = AsyncMock()

            # Execute
            result = await search_modules_impl(request, config)

            # Verify - module should be excluded (no stable versions)
            assert len(result.modules) == 0
            mock_terraform_client.get_module_versions.assert_called_once()

    @pytest.mark.asyncio
    async def test_stable_version_unchanged(self, mock_terraform_client, config):
        """Test that modules with stable versions are not modified."""
        # Setup - API returns module with stable version
        stable_response = {
            "modules": [
                {
                    "id": "terraform-ibm-modules/vpc/ibm",
                    "namespace": "terraform-ibm-modules",
                    "name": "vpc",
                    "provider": "ibm",
                    "version": "5.1.0",  # Stable
                    "description": "VPC module",
                    "source": "https://github.com/terraform-ibm-modules/terraform-ibm-vpc",
                    "downloads": 53004,
                    "verified": False,
                    "published_at": "2025-09-02T08:33:15.000Z",
                }
            ],
            "meta": {"limit": 100, "offset": 0, "total_count": 1},
        }

        mock_terraform_client.search_modules.side_effect = [
            stable_response,  # Counting phase
            stable_response,  # Validation phase
        ]

        request = ModuleSearchRequest(query="vpc", limit=1)  # 1 module available

        with (
            patch("tim_mcp.tools.search.TerraformClient") as mock_tf_class,
            patch("tim_mcp.tools.search.GitHubClient") as mock_gh_class,
            patch("tim_mcp.tools.search._is_repository_valid") as mock_is_valid,
        ):
            mock_tf_class.return_value.__aenter__.return_value = mock_terraform_client
            mock_gh_class.return_value.__aenter__.return_value = AsyncMock()
            mock_is_valid.return_value = True

            # Execute
            result = await search_modules_impl(request, config)

            # Verify - version should remain unchanged
            assert len(result.modules) == 1
            assert result.modules[0].version == "5.1.0"
            # get_module_versions should NOT be called for stable versions
            mock_terraform_client.get_module_versions.assert_not_called()


class TestRepositoryFiltering:
    """Test repository filtering functionality."""

    @pytest.fixture
    def config(self):
        """Create a test configuration."""
        return Config()

    @pytest.fixture
    def mock_terraform_client(self):
        """Create a mock Terraform client."""
        return AsyncMock()

    @pytest.fixture
    def mock_github_client(self):
        """Create a mock GitHub client."""
        mock_client = MagicMock()
        # parse_github_url is a regular method (not async)
        mock_client.parse_github_url.return_value = (
            "terraform-ibm-modules",
            "terraform-ibm-vpc",
        )
        # get_repository_info is async
        mock_client.get_repository_info = AsyncMock(
            return_value={
                "archived": False,
                "topics": ["core-team"],  # Required topic for valid repos
            }
        )
        return mock_client

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
            "meta": {"limit": 50, "offset": 0, "total_count": 23},
        }

    @pytest.mark.asyncio
    async def test_repository_filtering_valid_repos(
        self,
        config,
        mock_terraform_client,
        mock_github_client,
        sample_registry_response,
    ):
        """Test that valid repositories pass filtering."""
        # Setup
        mock_terraform_client.search_modules.side_effect = [
            sample_registry_response,  # Counting phase
            sample_registry_response,  # Validation phase
        ]

        # Mock GitHub client to return valid repository info
        def mock_parse_url(url):
            if "vpc" in url:
                return ("terraform-ibm-modules", "terraform-ibm-vpc")
            elif "security-group" in url:
                return ("terraform-ibm-modules", "terraform-ibm-security-group")
            return None

        mock_github_client.parse_github_url.side_effect = mock_parse_url

        # Mock repository info - both repos are valid
        mock_github_client.get_repository_info = AsyncMock(
            return_value={
                "archived": False,
                "topics": ["core-team"],  # Required topic for valid repos
            }
        )

        request = ModuleSearchRequest(query="vpc", limit=2)

        with (
            patch("tim_mcp.tools.search.TerraformClient") as mock_tf_class,
            patch("tim_mcp.tools.search.GitHubClient") as mock_gh_class,
        ):
            mock_tf_class.return_value.__aenter__.return_value = mock_terraform_client
            mock_gh_class.return_value.__aenter__.return_value = mock_github_client

            # Execute
            result = await search_modules_impl(request, config)

            # Verify
            assert len(result.modules) == 2  # Both modules should pass filtering
            assert result.modules[0].id == "terraform-ibm-modules/vpc/ibm"
            assert result.modules[1].id == "terraform-ibm-modules/security-group/ibm"

    @pytest.mark.asyncio
    async def test_repository_filtering_archived_repos(
        self,
        config,
        mock_terraform_client,
        mock_github_client,
        sample_registry_response,
    ):
        """Test that archived repositories are filtered out."""
        # Setup - vpc is archived, only security-group should pass
        mock_terraform_client.search_modules.side_effect = [
            sample_registry_response,  # Counting phase: 2 modules
            sample_registry_response,  # Validation phase: 2 modules, but only 1 passes filtering
        ]

        def mock_parse_url(url):
            if "vpc" in url:
                return ("terraform-ibm-modules", "terraform-ibm-vpc")
            elif "security-group" in url:
                return ("terraform-ibm-modules", "terraform-ibm-security-group")
            return None

        mock_github_client.parse_github_url.side_effect = mock_parse_url

        # Mock repository info - first repo is archived
        async def mock_get_repo_info(owner, repo):
            if "vpc" in repo:
                return {
                    "archived": True,  # This repo is archived
                    "topics": ["core-team"],
                }
            else:
                return {
                    "archived": False,
                    "topics": ["core-team"],  # Required topic for valid repos
                }

        mock_github_client.get_repository_info = AsyncMock(
            side_effect=mock_get_repo_info
        )

        request = ModuleSearchRequest(
            query="vpc", limit=1
        )  # Only 1 valid module available

        with (
            patch("tim_mcp.tools.search.TerraformClient") as mock_tf_class,
            patch("tim_mcp.tools.search.GitHubClient") as mock_gh_class,
        ):
            mock_tf_class.return_value.__aenter__.return_value = mock_terraform_client
            mock_gh_class.return_value.__aenter__.return_value = mock_github_client

            # Execute
            result = await search_modules_impl(request, config)

            # Verify - only non-archived repo should be in results (security-group)
            assert len(result.modules) == 1
            assert result.modules[0].id == "terraform-ibm-modules/security-group/ibm"

    @pytest.mark.asyncio
    async def test_repository_filtering_missing_topics(
        self,
        config,
        mock_terraform_client,
        mock_github_client,
        sample_registry_response,
    ):
        """Test that repositories without required topics are filtered out."""
        # Setup - vpc missing required topic, only security-group should pass
        mock_terraform_client.search_modules.side_effect = [
            sample_registry_response,  # Counting phase: 2 modules
            sample_registry_response,  # Validation phase: 2 modules, but only 1 passes filtering
        ]

        def mock_parse_url(url):
            if "vpc" in url:
                return ("terraform-ibm-modules", "terraform-ibm-vpc")
            elif "security-group" in url:
                return ("terraform-ibm-modules", "terraform-ibm-security-group")
            return None

        mock_github_client.parse_github_url.side_effect = mock_parse_url

        # Mock repository info - first repo missing core-team topic
        async def mock_get_repo_info(owner, repo):
            if "vpc" in repo:
                return {
                    "archived": False,
                    "topics": ["terraform", "ibm-cloud"],  # Missing core-team
                }
            else:
                return {
                    "archived": False,
                    "topics": ["core-team"],  # Required topic for valid repos
                }

        mock_github_client.get_repository_info = AsyncMock(
            side_effect=mock_get_repo_info
        )

        request = ModuleSearchRequest(
            query="vpc", limit=1
        )  # Only 1 valid module available

        with (
            patch("tim_mcp.tools.search.TerraformClient") as mock_tf_class,
            patch("tim_mcp.tools.search.GitHubClient") as mock_gh_class,
        ):
            mock_tf_class.return_value.__aenter__.return_value = mock_terraform_client
            mock_gh_class.return_value.__aenter__.return_value = mock_github_client

            # Execute
            result = await search_modules_impl(request, config)

            # Verify - only repo with required topics should be in results
            assert len(result.modules) == 1
            assert result.modules[0].id == "terraform-ibm-modules/security-group/ibm"


class TestGitHubClientURLParsing:
    """Test GitHub URL parsing functionality."""

    @pytest.fixture
    def mock_github_client(self):
        """Create a mock GitHub client with real URL parsing."""
        from tim_mcp.clients.github_client import GitHubClient
        from tim_mcp.config import Config

        return GitHubClient(Config())

    def test_parse_standard_github_url(self, mock_github_client):
        """Test parsing standard GitHub URLs."""
        url = "https://github.com/terraform-ibm-modules/terraform-ibm-vpc"
        result = mock_github_client.parse_github_url(url)
        assert result == ("terraform-ibm-modules", "terraform-ibm-vpc")

    def test_parse_github_url_with_git_suffix(self, mock_github_client):
        """Test parsing GitHub URLs with .git suffix."""
        url = "https://github.com/terraform-ibm-modules/terraform-ibm-vpc.git"
        result = mock_github_client.parse_github_url(url)
        assert result == ("terraform-ibm-modules", "terraform-ibm-vpc")

    def test_parse_github_url_with_git_prefix(self, mock_github_client):
        """Test parsing GitHub URLs with git:: prefix."""
        url = "git::https://github.com/terraform-ibm-modules/terraform-ibm-vpc.git"
        result = mock_github_client.parse_github_url(url)
        assert result == ("terraform-ibm-modules", "terraform-ibm-vpc")

    def test_parse_non_github_url(self, mock_github_client):
        """Test parsing non-GitHub URLs returns None."""
        url = "https://gitlab.com/owner/repo"
        result = mock_github_client.parse_github_url(url)
        assert result is None

    def test_parse_invalid_url(self, mock_github_client):
        """Test parsing invalid URLs returns None."""
        url = "not-a-valid-url"
        result = mock_github_client.parse_github_url(url)
        assert result is None

    def test_parse_empty_url(self, mock_github_client):
        """Test parsing empty URL returns None."""
        url = ""
        result = mock_github_client.parse_github_url(url)
        assert result is None


class TestModuleSearchRequestValidation:
    """Test validation of ModuleSearchRequest."""

    def test_valid_request(self):
        """Test valid request creation."""
        request = ModuleSearchRequest(query="vpc", limit=5)
        assert request.query == "vpc"
        assert request.limit == 5

    def test_default_limit(self):
        """Test default limit is applied."""
        request = ModuleSearchRequest(query="vpc")
        assert request.limit == 5

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
