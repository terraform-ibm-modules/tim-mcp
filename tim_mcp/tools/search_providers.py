"""
Provider search tool implementation for TIM-MCP.

This module provides the search_providers functionality for finding Terraform providers
in the Terraform Registry with comprehensive error handling and data transformation.
"""

from datetime import datetime
from typing import Any

from ..clients.terraform_client import TerraformClient
from ..config import Config
from ..exceptions import TIMError
from ..exceptions import ValidationError as TIMValidationError
from ..types import ProviderInfo, ProviderSearchRequest, ProviderSearchResponse


def _validate_api_response_structure(api_response: Any) -> None:
    """
    Validate the structure of the API response from Terraform Registry.

    Args:
        api_response: Raw API response to validate

    Raises:
        ValidationError: When the API response structure is invalid
    """
    if not isinstance(api_response, dict):
        raise TIMValidationError("Invalid API response format: expected dictionary")

    if "providers" not in api_response:
        raise TIMValidationError("Invalid API response format: missing 'providers' field")

    if "meta" not in api_response:
        raise TIMValidationError("Invalid API response format: missing 'meta' field")

    # Validate providers is a list
    if not isinstance(api_response["providers"], list):
        raise TIMValidationError(
            "Invalid API response format: 'providers' must be a list"
        )

    # Validate meta has required fields
    meta = api_response["meta"]
    if not isinstance(meta, dict):
        raise TIMValidationError(
            "Invalid API response format: 'meta' must be a dictionary"
        )


async def search_providers_impl(
    request: ProviderSearchRequest, config: Config
) -> ProviderSearchResponse:
    """
    Implementation function for the search_providers MCP tool.

    This function searches for Terraform providers in the registry using the provided
    search criteria and returns formatted results. It handles API communication,
    validates responses, and transforms data to match the tool specification.

    Args:
        request: The validated search request containing query parameters
        config: Configuration instance for client setup and behavior

    Returns:
        ProviderSearchResponse containing search results with properly formatted provider data

    Raises:
        TerraformRegistryError: When the Terraform Registry API fails
        RateLimitError: When API rate limits are exceeded
        ValidationError: When the API response format is invalid or malformed
    """
    from ..logging import get_logger

    logger = get_logger(__name__)

    # Create and use Terraform client as async context manager
    async with TerraformClient(config) as terraform_client:
        try:
            # Call the Terraform Registry API with search parameters
            api_response = await terraform_client.search_providers(
                query=request.query,
                limit=request.limit,
                offset=request.offset,
            )

            # Validate API response structure before processing
            _validate_api_response_structure(api_response)

            # Extract metadata from response
            meta = api_response["meta"]

            # Transform and validate each provider's data
            providers = []
            for i, provider_data in enumerate(api_response["providers"]):
                try:
                    provider = _transform_provider_data(provider_data)
                    providers.append(provider)
                except Exception as e:
                    # Include context about which provider failed
                    logger.warning(
                        f"Invalid provider data at index {i}: {e}",
                        provider_data=provider_data,
                    )
                    continue

            # Sort by downloads in descending order
            providers.sort(key=lambda p: p.downloads, reverse=True)

            logger.info(
                "Provider search completed",
                query=request.query,
                providers_found=len(providers),
                limit=request.limit,
                offset=request.offset,
            )

            # Create and return the formatted response
            return ProviderSearchResponse(
                query=request.query,
                total_found=len(providers),
                limit=request.limit,
                offset=request.offset,
                providers=providers,
            )

        except TIMError:
            # Re-raise TIM errors as-is to preserve error context
            raise
        except Exception as e:
            # Wrap unexpected errors with context
            raise TIMValidationError(
                f"Unexpected error processing search results: {e}"
            ) from e


def _transform_provider_data(provider_data: dict[str, Any]) -> ProviderInfo:
    """
    Transform raw provider data from the API into a ProviderInfo object.

    This function validates required fields, handles datetime conversion,
    and creates a properly typed ProviderInfo object.

    Args:
        provider_data: Raw provider data from the Terraform Registry API

    Returns:
        ProviderInfo object with validated and transformed data

    Raises:
        ValueError: When required fields are missing or invalid
        TypeError: When field types are unexpected
    """
    # Validate required fields exist
    required_fields = [
        "id",
        "namespace",
        "name",
        "version",
        "description",
        "source",
        "published_at",
    ]
    missing_fields = [field for field in required_fields if field not in provider_data]
    if missing_fields:
        raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

    # Transform the published_at datetime
    published_at_str = provider_data.get("published_at", "")
    if not published_at_str:
        raise ValueError("Missing or empty 'published_at' field")

    try:
        # Handle the ISO format with 'Z' suffix (common in Terraform Registry)
        if published_at_str.endswith("Z"):
            published_at_str = published_at_str[:-1] + "+00:00"
        published_at = datetime.fromisoformat(published_at_str)
    except (ValueError, TypeError) as e:
        raise ValueError(
            f"Invalid published_at format '{published_at_str}': {e}"
        ) from e

    # Validate and get optional fields with defaults
    downloads = provider_data.get("downloads", 0)
    if not isinstance(downloads, int) or downloads < 0:
        downloads = 0  # Fallback to 0 for invalid download counts

    tier = provider_data.get("tier", "community")
    if not isinstance(tier, str):
        tier = "community"  # Fallback to community for invalid tier

    # Create and return the ProviderInfo object
    # Pydantic will perform additional validation on the fields
    try:
        return ProviderInfo(
            id=provider_data["id"],
            namespace=provider_data["namespace"],
            name=provider_data["name"],
            version=provider_data["version"],
            description=provider_data["description"],
            source_url=provider_data["source"],  # Pydantic validates as HttpUrl
            downloads=downloads,
            tier=tier,
            published_at=published_at,
        )
    except Exception as e:
        raise ValueError(f"Failed to create ProviderInfo object: {e}") from e