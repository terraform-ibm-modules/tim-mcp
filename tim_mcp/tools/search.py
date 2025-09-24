"""
Search tool implementation for TIM-MCP.

This module provides the search_modules functionality for finding Terraform modules
in the Terraform Registry with comprehensive error handling and data transformation.

The implementation follows these principles:
- Comprehensive input validation using Pydantic models
- Graceful error handling with appropriate exception types
- Proper async context manager usage for resource cleanup
- Data transformation to match the tool specification format
"""

from datetime import datetime
from typing import Any

from ..clients.terraform_client import TerraformClient
from ..config import Config
from ..exceptions import TIMError
from ..exceptions import ValidationError as TIMValidationError
from ..types import ModuleInfo, ModuleSearchRequest, ModuleSearchResponse


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

    if "modules" not in api_response:
        raise TIMValidationError("Invalid API response format: missing 'modules' field")

    if "meta" not in api_response:
        raise TIMValidationError("Invalid API response format: missing 'meta' field")

    # Validate modules is a list
    if not isinstance(api_response["modules"], list):
        raise TIMValidationError(
            "Invalid API response format: 'modules' must be a list"
        )

    # Validate meta has required fields
    meta = api_response["meta"]
    if not isinstance(meta, dict):
        raise TIMValidationError(
            "Invalid API response format: 'meta' must be a dictionary"
        )


async def search_modules_impl(
    request: ModuleSearchRequest, config: Config
) -> ModuleSearchResponse:
    """
    Implementation function for the search_modules MCP tool.

    This function searches for Terraform modules in the registry using the provided
    search criteria and returns formatted results. It handles API communication,
    validates responses, and transforms data to match the tool specification.

    Args:
        request: The validated search request containing query parameters
        config: Configuration instance for client setup and behavior

    Returns:
        ModuleSearchResponse containing search results with properly formatted module data

    Raises:
        TerraformRegistryError: When the Terraform Registry API fails
        RateLimitError: When API rate limits are exceeded
        ValidationError: When the API response format is invalid or malformed
    """
    from ..logging import get_logger

    logger = get_logger(__name__)

    # Use the configured namespace (always the first allowed namespace)
    namespace = config.allowed_namespaces[0] if config.allowed_namespaces else None

    # Create and use the Terraform client as async context manager
    # This ensures proper cleanup of HTTP connections
    async with TerraformClient(config) as client:
        try:
            # Call the Terraform Registry API with search parameters
            api_response = await client.search_modules(
                query=request.query,
                namespace=namespace,
                limit=request.limit,
                offset=0,  # Start from beginning - pagination can be added later
            )

            # Validate API response structure before processing
            _validate_api_response_structure(api_response)

            # Extract metadata from response
            meta = api_response["meta"]
            total_count = meta.get("total_count", 0)

            # Transform each module's data to our format
            modules = []
            for i, module_data in enumerate(api_response["modules"]):
                try:
                    module = _transform_module_data(module_data)
                    # Apply module exclusion filtering
                    if not _is_module_excluded(module.id, config.excluded_modules):
                        modules.append(module)
                    else:
                        logger.info("Module excluded from results", module_id=module.id)
                except Exception as e:
                    # Include context about which module failed
                    raise TIMValidationError(
                        f"Invalid module data at index {i}: {e}"
                    ) from e

            # Create and return the formatted response
            return ModuleSearchResponse(
                query=request.query, total_found=total_count, modules=modules
            )

        except TIMError:
            # Re-raise TIM errors as-is to preserve error context
            raise
        except Exception as e:
            # Wrap unexpected errors with context
            raise TIMValidationError(
                f"Unexpected error processing search results: {e}"
            ) from e


def _transform_module_data(module_data: dict[str, Any]) -> ModuleInfo:
    """
    Transform raw module data from the API into a ModuleInfo object.

    This function validates required fields, handles datetime conversion,
    and creates a properly typed ModuleInfo object.

    Args:
        module_data: Raw module data from the Terraform Registry API

    Returns:
        ModuleInfo object with validated and transformed data

    Raises:
        ValueError: When required fields are missing or invalid
        TypeError: When field types are unexpected
    """
    # Validate required fields exist
    required_fields = [
        "id",
        "namespace",
        "name",
        "provider",
        "version",
        "description",
        "source",
    ]
    missing_fields = [field for field in required_fields if field not in module_data]
    if missing_fields:
        raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

    # Transform the published_at datetime
    published_at_str = module_data.get("published_at", "")
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
    downloads = module_data.get("downloads", 0)
    if not isinstance(downloads, int) or downloads < 0:
        downloads = 0  # Fallback to 0 for invalid download counts

    verified = module_data.get("verified", False)
    if not isinstance(verified, bool):
        verified = False  # Fallback to False for invalid verification status

    # Create and return the ModuleInfo object
    # Pydantic will perform additional validation on the fields
    try:
        return ModuleInfo(
            id=module_data["id"],
            namespace=module_data["namespace"],
            name=module_data["name"],
            provider=module_data["provider"],
            version=module_data["version"],
            description=module_data["description"],
            source_url=module_data["source"],  # Pydantic validates as HttpUrl
            downloads=downloads,
            verified=verified,
            published_at=published_at,
        )
    except Exception as e:
        raise ValueError(f"Failed to create ModuleInfo object: {e}") from e


def _is_module_excluded(module_id: str, excluded_modules: list[str]) -> bool:
    """
    Check if a module ID is in the exclusion list.

    Args:
        module_id: The full module identifier (e.g., "terraform-ibm-modules/vpc/ibm")
        excluded_modules: List of module IDs to exclude

    Returns:
        True if the module should be excluded, False otherwise
    """
    return module_id in excluded_modules
