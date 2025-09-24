"""
Module details tool implementation for TIM-MCP.

This tool retrieves comprehensive module information from the Terraform Registry
and formats it as markdown for easy consumption.
"""

from datetime import datetime
from typing import Any

from ..clients.terraform_client import TerraformClient
from ..config import Config
from ..exceptions import (
    ModuleNotFoundError,  # pylint: disable=redefined-builtin
    TerraformRegistryError,
    ValidationError,
)
from ..types import ModuleDetailsRequest


def parse_module_id(module_id: str) -> tuple[str, str, str]:
    """
    Parse a module ID into its components.

    Args:
        module_id: Full module identifier (e.g., "terraform-ibm-modules/vpc/ibm")

    Returns:
        Tuple of (namespace, name, provider)

    Raises:
        ValidationError: If module_id format is invalid
    """
    if not module_id or not isinstance(module_id, str):
        raise ValidationError("module_id cannot be empty", field="module_id")

    parts = module_id.split("/")

    if len(parts) != 3:
        raise ValidationError(
            f"Invalid module_id format. Expected 'namespace/name/provider', got '{module_id}'",
            field="module_id",
        )

    namespace, name, provider = parts

    if not all([namespace.strip(), name.strip(), provider.strip()]):
        raise ValidationError("module_id components cannot be empty", field="module_id")

    return namespace.strip(), name.strip(), provider.strip()


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
    return ", ".join(f"v{version}" for version in versions)


def format_inputs(inputs: list[dict[str, Any]]) -> tuple[str, str]:
    """
    Format inputs into required and optional sections.

    Args:
        inputs: List of input variable dictionaries

    Returns:
        Tuple of (required_inputs_text, optional_inputs_text)
    """
    if not inputs:
        return "None", "None"

    required = []
    optional = []

    for input_var in inputs:
        name = input_var.get("name", "")
        var_type = input_var.get("type", "string")
        description = input_var.get("description", "No description")
        is_required = input_var.get("required", True)
        default = input_var.get("default")

        # Clean up the description
        description = description.strip() if description else "No description"

        formatted_line = f"- **{name}** ({var_type}): {description}"

        if not is_required and default is not None:
            formatted_line += f" (default: {default})"

        if is_required:
            required.append(formatted_line)
        else:
            optional.append(formatted_line)

    required_text = "\n".join(required) if required else "None"
    optional_text = "\n".join(optional) if optional else "None"

    return required_text, optional_text


def format_outputs(outputs: list[dict[str, Any]]) -> str:
    """
    Format outputs section.

    Args:
        outputs: List of output variable dictionaries

    Returns:
        Formatted outputs as markdown string
    """
    if not outputs:
        return "None"

    formatted = []
    for output in outputs:
        name = output.get("name", "")
        output_type = output.get("type", "string")
        description = output.get("description", "No description").strip()

        formatted.append(f"- **{name}** ({output_type}): {description}")

    return "\n".join(formatted)


def format_dependencies(dependencies: list[dict[str, Any]]) -> tuple[str, str]:
    """
    Format dependencies into provider and module sections.

    Args:
        dependencies: List of dependency dictionaries

    Returns:
        Tuple of (provider_deps_text, module_deps_text)
    """
    if not dependencies:
        return "None", "None"

    provider_deps = []
    module_deps = []

    # Map of common provider names to their display names
    provider_display_names = {
        "aws": "AWS",
        "azurerm": "Azure",
        "azuread": "Azure AD",
        "google": "Google Cloud",
        "ibm": "IBM Cloud",
        "kubernetes": "Kubernetes",
        "helm": "Helm",
        "tls": "TLS",
        "random": "Random",
        "null": "Null",
        "template": "Template",
        "local": "Local",
        "external": "External",
    }

    for dep in dependencies:
        name = dep.get("name", "")
        version = dep.get("version", "")

        if not name:
            continue

        # Check if it's a provider (simple name) or module (namespace/name/provider)
        if "/" in name:
            # Module dependency
            module_deps.append(f"- {name} {version}")
        else:
            # Provider dependency - format nicely
            provider_name = provider_display_names.get(name.lower(), name.title())
            provider_deps.append(f"- {provider_name} Provider {version}")

    provider_text = "\n".join(provider_deps) if provider_deps else "None"
    module_text = "\n".join(module_deps) if module_deps else "None"

    return provider_text, module_text


def format_module_details(module_data: dict[str, Any], versions: list[str]) -> str:
    """
    Format module details as comprehensive markdown.

    Args:
        module_data: Module data from Terraform Registry API
        versions: List of available versions

    Returns:
        Formatted markdown string

    Raises:
        ValueError: If required fields are missing
    """
    # Extract basic module information with defaults
    module_id = module_data.get("id", "Unknown Module")
    version = module_data.get("version", "Unknown")
    description = module_data.get("description", "No description available").strip()
    source = module_data.get("source", "")
    downloads = module_data.get("downloads", 0)
    published_at = module_data.get("published_at", "")

    # Validate required fields
    if not module_id or module_id == "Unknown Module":
        raise ValueError("Module ID is required but missing from response")

    # Extract root module information
    root = module_data.get("root", {})
    inputs = root.get("inputs", [])
    outputs = root.get("outputs", [])
    dependencies = root.get("dependencies", [])

    # Format sections
    required_inputs, optional_inputs = format_inputs(inputs)
    formatted_outputs = format_outputs(outputs)
    provider_deps, module_deps = format_dependencies(dependencies)

    # Build comprehensive markdown
    markdown = f"""# {module_id} - Module Details

**Latest Version:** v{version}
**Published:** {format_published_date(published_at)}
**Downloads:** {format_download_count(downloads)}
**Source:** {source}

## Description
{description}

## Required Inputs
{required_inputs}

## Optional Inputs
{optional_inputs}

## Outputs
{formatted_outputs}

## Dependencies
**Provider Requirements:**
{provider_deps}

**Module Dependencies:** {module_deps}

## Available Versions
{format_version_list(versions)}"""

    return markdown


async def get_module_details_impl(request: ModuleDetailsRequest, config: Config) -> str:
    """
    Implementation function for the get_module_details MCP tool.

    This function retrieves comprehensive module information from the Terraform Registry,
    including metadata, inputs, outputs, dependencies, and available versions.

    Args:
        request: Module details request containing module_id and optional version
        config: Configuration instance with API settings

    Returns:
        Formatted module details as markdown string

    Raises:
        ValidationError: If module_id format is invalid
        ModuleNotFoundError: If module is not found in the registry
        TerraformRegistryError: If API request fails or returns invalid data
    """
    # Parse and validate module ID
    try:
        namespace, name, provider = parse_module_id(request.module_id)
    except ValidationError as e:
        # Re-raise validation errors with original context
        raise TerraformRegistryError(f"Module ID validation failed: {e}") from e

    # Initialize Terraform client and fetch data
    async with TerraformClient(config) as terraform_client:
        try:
            # Fetch module details and versions concurrently for better performance
            # Note: We could use asyncio.gather here, but sequential is fine for this use case
            # and provides better error isolation

            # Get module details for the specified version
            module_data = await terraform_client.get_module_details(
                namespace=namespace,
                name=name,
                provider=provider,
                version=request.version,
            )

            # Get available versions for the module
            versions = await terraform_client.get_module_versions(
                namespace=namespace, name=name, provider=provider
            )

            # Format as comprehensive markdown
            try:
                return format_module_details(module_data, versions)
            except ValueError as e:
                # Convert formatting errors to TerraformRegistryError
                raise TerraformRegistryError(
                    f"Invalid module data received from registry: {e}"
                ) from e

        except TerraformRegistryError as e:
            # Transform 404 errors to more specific ModuleNotFoundError
            if e.status_code == 404:
                raise ModuleNotFoundError(
                    request.module_id,
                    version=request.version if request.version != "latest" else None,
                ) from e
            # Re-raise other registry errors unchanged
            raise
