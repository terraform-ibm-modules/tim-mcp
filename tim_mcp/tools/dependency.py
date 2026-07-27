"""
Module dependency tool implementation for TIM-MCP.

This tool retrieves all required provider and module dependencies for a given
Terraform module (root + submodules) from the Terraform Registry and formats
them as markdown.
"""

from typing import Any

from ..clients.terraform_client import TerraformClient
from ..config import Config
from ..context import get_cache, get_rate_limiter
from ..exceptions import ModuleNotFoundError, TerraformRegistryError, ValidationError
from ..types import ModuleDependencyRequest
from ..utils.module_id import parse_module_id_with_version
from .details import format_dependencies


def format_module_dependencies(module_data: dict[str, Any]) -> str:
    """
    Format all dependencies of a module as markdown.

    Covers the root module and every submodule that declares dependencies.
    Uses the same keys as details.py:
      - root["dependencies"]          → module dependencies
      - root["provider_dependencies"] → provider requirements

    Args:
        module_data: Module data dict returned by the Terraform Registry API.

    Returns:
        Formatted markdown string listing all dependencies.
    """
    module_id = module_data.get("id", "Unknown Module")
    version = module_data.get("version", "Unknown")

    # Root module — mirror details.py key usage exactly
    root = module_data.get("root", {})
    dependencies = root.get("dependencies", [])
    provider_dependencies = root.get("provider_dependencies", [])

    _, module_dep_text = format_dependencies(dependencies)
    provider_text, _ = format_dependencies(provider_dependencies)

    # Submodule dependencies — always list every submodule regardless of whether
    # it has dependencies, so submodules are never silently hidden
    submodule_sections: list[str] = []
    for submodule in module_data.get("submodules", []):
        sub_path = submodule.get("path", "unknown")
        sub_deps = submodule.get("dependencies", [])
        sub_provider_deps = submodule.get("provider_dependencies", [])
        _, sub_module_text = format_dependencies(sub_deps)
        sub_provider_text, _ = format_dependencies(sub_provider_deps)
        submodule_sections.append(
            f"### Submodule: `{sub_path}`\n"
            f"**Provider Requirements:**\n{sub_provider_text}\n\n"
            f"**Module Dependencies:**\n{sub_module_text}"
        )

    submodule_block = (
        "\n\n".join(submodule_sections) if submodule_sections else "_None_"
    )

    return f"""# {module_id} v{version} - Dependencies

## Root Module

**Provider Requirements:**
{provider_text}

**Module Dependencies:**
{module_dep_text}

## Submodule Dependencies
{submodule_block}"""


async def get_module_dependency_impl(
    request: ModuleDependencyRequest, config: Config
) -> str:
    """
    Implementation function for the get_module_dependency MCP tool.

    Uses the same fetch pattern as get_module_details_impl in details.py,
    then formats only the dependency sections.

    Args:
        request: Module dependency request containing module_id and optional version.
        config: Configuration instance with API settings.

    Returns:
        Formatted markdown string listing all dependencies.

    Raises:
        ValidationError: If module_id format is invalid.
        ModuleNotFoundError: If the module is not found in the registry.
        TerraformRegistryError: If the API request fails or returns invalid data.
    """
    # Parse and validate module ID with version — same pattern as details.py
    try:
        namespace, name, provider, version = parse_module_id_with_version(
            request.module_id
        )
    except ValidationError as e:
        # Re-raise validation errors with original context
        raise TerraformRegistryError(f"Module ID validation failed: {e}") from e

    # Initialize Terraform client and fetch data — same pattern as details.py
    cache = get_cache()
    rate_limiter = get_rate_limiter()
    async with TerraformClient(
        config, cache=cache, rate_limiter=rate_limiter
    ) as terraform_client:
        try:
            # Get module details for the specified version
            module_data = await terraform_client.get_module_details(
                namespace=namespace,
                name=name,
                provider=provider,
                version=version,
            )

            # Format only the dependency sections
            try:
                return format_module_dependencies(module_data)
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
                    version=version if version != "latest" else None,
                ) from e
            # Re-raise other registry errors unchanged
            raise
