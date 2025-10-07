"""
Provider details tool implementation for TIM-MCP.

This tool retrieves comprehensive provider information from the Terraform Registry
and formats it as markdown for easy consumption.
"""

from datetime import datetime
from typing import Any

from ..clients.terraform_client import TerraformClient
from ..config import Config
from ..exceptions import TerraformRegistryError, ValidationError
from ..types import ProviderDetailsRequest


def parse_provider_id_with_version(provider_id: str) -> tuple[str, str, str]:
    """
    Parse provider ID with optional version into components.

    Supports formats:
    - namespace/name -> (namespace, name, "latest")
    - namespace/name/version -> (namespace, name, version)

    Args:
        provider_id: Provider identifier string

    Returns:
        Tuple of (namespace, name, version)

    Raises:
        ValidationError: If the provider ID format is invalid
    """
    parts = provider_id.strip().split("/")

    if len(parts) == 2:
        # Format: namespace/name
        namespace, name = parts
        return namespace, name, "latest"
    elif len(parts) == 3:
        # Format: namespace/name/version
        namespace, name, version = parts
        return namespace, name, version
    else:
        raise ValidationError(
            f"Invalid provider_id format: '{provider_id}'. "
            f"Expected 'namespace/name' or 'namespace/name/version'"
        )


def format_download_count(count: int) -> str:
    """Format download count with commas for readability."""
    return f"{count:,}"


def format_published_date(date_str: str) -> str:
    """
    Format published date to YYYY-MM-DD.

    Handles various ISO 8601 formats commonly returned by APIs.
    """
    if not date_str:
        return "Unknown"

    try:
        # Normalize the date string
        normalized = date_str.replace("Z", "+00:00")

        # Handle microseconds by truncating them
        if "." in normalized:
            normalized = normalized.split(".")[0] + "+00:00"

        # Parse and format
        dt = datetime.fromisoformat(normalized)
        return dt.strftime("%Y-%m-%d")
    except (ValueError, AttributeError, TypeError):
        # Fallback: try to extract date part if it looks like YYYY-MM-DD
        if len(date_str) >= 10 and date_str[4] == "-" and date_str[7] == "-":
            return date_str[:10]
        return "Invalid date"


def format_version_list(versions: list[str]) -> str:
    """Format version list with 'v' prefix."""
    if not versions:
        return "No versions available"

    # Limit to most recent 10 versions if there are many
    display_versions = versions[-10:] if len(versions) > 10 else versions
    formatted = ", ".join(f"v{version}" for version in reversed(display_versions))

    if len(versions) > 10:
        formatted = f"{formatted} (showing latest 10 of {len(versions)} versions)"

    return formatted


def format_provider_details(provider_data: dict[str, Any]) -> str:
    """
    Format provider details as comprehensive markdown.

    Args:
        provider_data: Provider data from Terraform Registry API

    Returns:
        Formatted markdown string

    Raises:
        ValueError: If required fields are missing
    """
    # Extract basic provider information with defaults
    provider_id = provider_data.get("id", "Unknown Provider")
    namespace = provider_data.get("namespace", "Unknown")
    name = provider_data.get("name", "Unknown")
    version = provider_data.get("version", "Unknown")
    description = provider_data.get("description", "No description available").strip()
    source = provider_data.get("source", "")
    downloads = provider_data.get("downloads", 0)
    published_at = provider_data.get("published_at", "")
    tier = provider_data.get("tier", "community")

    # Validate required fields
    if not provider_id or provider_id == "Unknown Provider":
        raise ValueError("Provider ID is required but missing from response")

    # Extract versions list
    versions = provider_data.get("versions", [])

    # Build comprehensive markdown
    markdown = f"""# {namespace}/{name} - Provider Details

**Latest Version:** v{version}
**Tier:** {tier.capitalize()}
**Published:** {format_published_date(published_at)}
**Downloads:** {format_download_count(downloads)}
**Source:** {source}

## Description
{description}

## Available Versions
{format_version_list(versions)}

## Usage
To use this provider in your Terraform configuration:

```hcl
terraform {{
  required_providers {{
    {name} = {{
      source  = "{namespace}/{name}"
      version = "~> {version}"
    }}
  }}
}}

provider "{name}" {{
  # Configuration options
}}
```

## Documentation
For detailed documentation, visit: https://registry.terraform.io/providers/{namespace}/{name}/latest/docs"""

    return markdown


def _is_provider_allowed(namespace: str, name: str, config: Config) -> bool:
    """
    Check if a provider is in the allowlist.

    Args:
        namespace: Provider namespace
        name: Provider name
        config: Configuration instance with allowlist settings

    Returns:
        True if provider is allowed, False otherwise
    """
    # Check if namespace is allowed
    if namespace in config.allowed_provider_namespaces:
        return True

    # Check if specific provider ID is allowed (namespace/name format)
    provider_id = f"{namespace}/{name}"
    if provider_id in config.allowed_provider_ids:
        return True

    return False


async def get_provider_details_impl(
    request: ProviderDetailsRequest, config: Config
) -> str:
    """
    Implementation function for the get_provider_details MCP tool.

    This function retrieves comprehensive provider information from the Terraform Registry,
    including metadata, versions, and usage examples.

    Args:
        request: Provider details request containing provider_id and optional version
        config: Configuration instance with API settings

    Returns:
        Formatted provider details as markdown string

    Raises:
        ValidationError: If provider_id format is invalid or provider is not allowlisted
        TerraformRegistryError: If API request fails or returns invalid data
    """
    # Parse and validate provider ID with version
    try:
        namespace, name, version = parse_provider_id_with_version(request.provider_id)
    except ValidationError as e:
        # Re-raise validation errors with original context
        raise TerraformRegistryError(f"Provider ID validation failed: {e}") from e

    # Validate provider is in allowlist
    if not _is_provider_allowed(namespace, name, config):
        raise ValidationError(
            f"Provider '{namespace}/{name}' is not in the allowlist. "
            f"Only providers from the following namespaces are allowed: "
            f"{', '.join(config.allowed_provider_namespaces)}. "
            f"Specific allowed providers: {', '.join(config.allowed_provider_ids)}."
        )

    # Initialize Terraform client and fetch data
    async with TerraformClient(config) as terraform_client:
        try:
            # Get provider details for the specified version
            provider_data = await terraform_client.get_provider_details(
                namespace=namespace,
                name=name,
                version=version,
            )

            # Format as comprehensive markdown
            try:
                return format_provider_details(provider_data)
            except ValueError as e:
                # Convert formatting errors to TerraformRegistryError
                raise TerraformRegistryError(
                    f"Invalid provider data received from registry: {e}"
                ) from e

        except TerraformRegistryError as e:
            # Transform 404 errors to more descriptive messages
            if e.status_code == 404:
                version_msg = f" (version {version})" if version != "latest" else ""
                raise TerraformRegistryError(
                    f"Provider '{namespace}/{name}'{version_msg} not found in registry",
                    status_code=404,
                ) from e
            # Re-raise other registry errors unchanged
            raise
