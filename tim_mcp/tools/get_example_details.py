"""
Example details tool implementation for TIM-MCP.

This tool retrieves detailed information about specific examples from the
Terraform Registry API, including inputs, outputs, dependencies, and README content.
"""

from typing import Any

from ..clients.terraform_client import TerraformClient
from ..config import Config
from ..exceptions import ModuleNotFoundError, TerraformRegistryError
from ..exceptions import ValidationError
from ..logging import get_logger
from ..types import GetExampleDetailsRequest
from ..utils.module_id import parse_module_id_with_version

logger = get_logger(__name__)


def format_example_inputs(inputs: list[dict[str, Any]]) -> tuple[str, str]:
    """
    Format example inputs into required and optional sections.

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

        formatted_line = f"- **{name}** (`{var_type}`): {description}"

        if not is_required and default is not None:
            # Format default value
            if isinstance(default, str):
                formatted_line += f" (default: `{default}`)"
            else:
                formatted_line += f" (default: `{default}`)"

        if is_required:
            required.append(formatted_line)
        else:
            optional.append(formatted_line)

    required_text = "\n".join(required) if required else "None"
    optional_text = "\n".join(optional) if optional else "None"

    return required_text, optional_text


def format_example_outputs(outputs: list[dict[str, Any]]) -> str:
    """
    Format example outputs section.

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
        description = output.get("description", "No description").strip()

        formatted.append(f"- **{name}**: {description}")

    return "\n".join(formatted)


def format_example_dependencies(
    provider_deps: list[dict[str, Any]], module_deps: list[dict[str, Any]]
) -> tuple[str, str]:
    """
    Format example dependencies into provider and module sections.

    Args:
        provider_deps: List of provider dependency dictionaries
        module_deps: List of module dependency dictionaries

    Returns:
        Tuple of (provider_deps_text, module_deps_text)
    """
    # Format provider dependencies
    provider_lines = []
    if provider_deps:
        for dep in provider_deps:
            name = dep.get("name", "")
            version = dep.get("version", "")
            source = dep.get("source", "")

            if name:
                if source:
                    provider_lines.append(f"- **{name}** (`{source}`): {version}")
                else:
                    provider_lines.append(f"- **{name}**: {version}")

    provider_text = "\n".join(provider_lines) if provider_lines else "None"

    # Format module dependencies
    module_lines = []
    if module_deps:
        for dep in module_deps:
            name = dep.get("name", "")
            source = dep.get("source", "")
            version = dep.get("version", "")

            if source:
                module_lines.append(f"- **{name}**: `{source}` {version}")
            elif name:
                module_lines.append(f"- **{name}**: {version}")

    module_text = "\n".join(module_lines) if module_lines else "None"

    return provider_text, module_text


def format_example_resources(resources: list[dict[str, Any]]) -> str:
    """
    Format example resources section.

    Args:
        resources: List of resource dictionaries

    Returns:
        Formatted resources as markdown string
    """
    if not resources:
        return "None"

    formatted = []
    for resource in resources:
        name = resource.get("name", "")
        resource_type = resource.get("type", "")

        if name and resource_type:
            formatted.append(f"- **{name}** (`{resource_type}`)")
        elif resource_type:
            formatted.append(f"- `{resource_type}`")

    return "\n".join(formatted) if formatted else "None"


def format_example_details(
    example_data: dict[str, Any], module_id: str, version: str
) -> str:
    """
    Format example details as comprehensive markdown.

    Args:
        example_data: Example data from Terraform Registry API
        module_id: Module identifier
        version: Module version

    Returns:
        Formatted markdown string

    Raises:
        ValueError: If required fields are missing
    """
    # Extract basic example information
    example_path = example_data.get("path", "")
    example_name = example_data.get("name", "")
    readme = example_data.get("readme", "")

    if not example_path:
        raise ValueError("Example path is required but missing from response")

    # Extract example details
    inputs = example_data.get("inputs", [])
    outputs = example_data.get("outputs", [])
    dependencies = example_data.get("dependencies", [])
    provider_dependencies = example_data.get("provider_dependencies", [])
    resources = example_data.get("resources", [])

    # Format sections
    required_inputs, optional_inputs = format_example_inputs(inputs)
    formatted_outputs = format_example_outputs(outputs)
    provider_deps, module_deps = format_example_dependencies(
        provider_dependencies, dependencies
    )
    formatted_resources = format_example_resources(resources)

    # Extract README summary (first paragraph or up to 3 lines)
    readme_summary = "No description available"
    if readme:
        lines = [line.strip() for line in readme.split("\n") if line.strip()]
        # Skip title lines starting with #
        content_lines = [line for line in lines if not line.startswith("#")]
        if content_lines:
            # Take first few lines as summary
            readme_summary = " ".join(content_lines[:3])
            # Limit to reasonable length
            if len(readme_summary) > 300:
                readme_summary = readme_summary[:300] + "..."

    # Build comprehensive markdown
    markdown = f"""# {module_id} - Example: {example_name}

**Path:** `{example_path}`
**Version:** v{version}

## Description
{readme_summary}

## Required Inputs
{required_inputs}

## Optional Inputs
{optional_inputs}

## Outputs
{formatted_outputs}

## Dependencies

### Provider Requirements
{provider_deps}

### Module Dependencies
{module_deps}

## Resources Created
{formatted_resources}

## Full README

{readme if readme else "No README available"}"""

    return markdown


async def get_example_details_impl(
    request: GetExampleDetailsRequest, config: Config
) -> str:
    """
    Implementation function for the get_example_details MCP tool.

    This function retrieves detailed information about a specific example from
    the Terraform Registry, including inputs, outputs, dependencies, and README.

    Args:
        request: Example details request containing module_id and example_path
        config: Configuration instance with API settings

    Returns:
        Formatted example details as markdown string

    Raises:
        ValidationError: If module_id format is invalid
        ModuleNotFoundError: If module or example is not found
        TerraformRegistryError: If API request fails or returns invalid data
    """
    # Parse and validate module ID with version
    try:
        namespace, name, provider, version = parse_module_id_with_version(
            request.module_id
        )
    except ValidationError as e:
        # Re-raise validation errors with original context
        raise TerraformRegistryError(f"Module ID validation failed: {e}") from e

    base_module_id = f"{namespace}/{name}/{provider}"

    # Initialize Terraform client and fetch data
    async with TerraformClient(config) as terraform_client:
        try:
            # Get module structure which includes examples
            module_data = await terraform_client.get_module_structure(
                namespace=namespace, name=name, provider=provider, version=version
            )

            # Extract version from response
            resolved_version = module_data.get("version", version)

            # Find the specific example by path
            examples = module_data.get("examples", [])
            example_data = None

            for example in examples:
                if example.get("path") == request.example_path:
                    example_data = example
                    break

            if not example_data:
                # Example not found
                raise ModuleNotFoundError(
                    request.module_id,
                    version=version if version != "latest" else None,
                    details={
                        "reason": f"Example not found at path: {request.example_path}",
                        "available_examples": [e.get("path") for e in examples],
                    },
                )

            # Format as comprehensive markdown
            try:
                return format_example_details(
                    example_data, base_module_id, resolved_version
                )
            except ValueError as e:
                # Convert formatting errors to TerraformRegistryError
                raise TerraformRegistryError(
                    f"Invalid example data received from registry: {e}"
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