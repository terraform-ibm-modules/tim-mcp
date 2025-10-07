"""
TIM-MCP Server.

This module implements the main MCP server using FastMCP with tools
for Terraform IBM Modules discovery and implementation support.
"""

import json
import time
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from pydantic import ValidationError

from .config import Config, load_config
from .exceptions import TIMError
from .exceptions import ValidationError as TIMValidationError
from .logging import configure_logging, get_logger, log_tool_execution
from .types import (
    GetContentRequest,
    ListContentRequest,
    ModuleDetailsRequest,
    ModuleSearchRequest,
    ProviderDetailsRequest,
    ProviderSearchRequest,
)

# Global configuration and logger
config: Config = load_config()
configure_logging(config)
logger = get_logger(__name__)


def _load_instructions() -> str:
    """Load instructions from the static instructions file."""
    # First try the packaged location (when installed via pip/uvx)
    packaged_path = Path(__file__).parent / "static" / "instructions.md"
    # Then try the development location (when running from source)
    dev_path = Path(__file__).parent.parent / "static" / "instructions.md"

    for instructions_path in [packaged_path, dev_path]:
        if instructions_path.exists():
            try:
                return instructions_path.read_text(encoding="utf-8")
            except Exception as e:
                logger.error(
                    f"Error reading instructions file at {instructions_path}: {e}"
                )
                continue

    # If neither path works, provide helpful error message
    logger.error(f"Instructions file not found at {packaged_path} or {dev_path}")
    raise FileNotFoundError(
        f"Required instructions file not found. Searched locations:\n"
        f"  - {packaged_path} (packaged installation)\n"
        f"  - {dev_path} (development installation)\n"
        f"Please ensure the instructions.md file exists in the static directory."
    )


# Initialize FastMCP server
mcp = FastMCP(
    "TIM-MCP",
    instructions=_load_instructions(),
)


def _sanitize_list_parameter(param: Any, param_name: str) -> list[str] | None:
    """
    Sanitize list parameters that might be passed as JSON strings by LLMs.

    This function handles parameter conversion without modifying the patterns themselves,
    since the underlying implementation uses pathlib.Path.match() for glob matching.

    Args:
        param: The parameter value to sanitize
        param_name: Name of the parameter for logging

    Returns:
        Sanitized list of patterns or None

    Raises:
        ValueError: If the parameter cannot be converted to a proper format
    """
    if param is None:
        return None

    def _process_pattern_list(patterns: list[str]) -> list[str]:
        """Process a list of patterns, keeping them as-is for glob matching."""
        return patterns

    if isinstance(param, list):
        # Validate all items are strings
        if not all(isinstance(item, str) for item in param):
            raise ValueError(
                f"Parameter {param_name} must be a list of strings, None, or a JSON array string"
            )
        return _process_pattern_list(param)

    if isinstance(param, str):
        # Check if it looks like a JSON array
        param_stripped = param.strip()
        if param_stripped.startswith("[") and param_stripped.endswith("]"):
            try:
                parsed = json.loads(param_stripped)
                if isinstance(parsed, list) and all(
                    isinstance(item, str) for item in parsed
                ):
                    logger.warning(
                        f"Parameter {param_name} was passed as JSON string, auto-converted to list",
                        original_value=param,
                        converted_value=parsed,
                    )
                    return _process_pattern_list(parsed)
            except json.JSONDecodeError:
                pass

        # If it's a single string that's not JSON, convert to single-item list
        logger.warning(
            f"Parameter {param_name} was passed as string, converting to single-item list",
            original_value=param,
        )
        return _process_pattern_list([param])

    raise ValueError(
        f"Parameter {param_name} must be a list of strings, None, or a JSON array string"
    )


@mcp.tool()
async def search_modules(
    query: str,
    limit: int = 5,
) -> str:
    """
    Search Terraform Registry for modules with intelligent result optimization.

    SEARCH TIPS:
    - Use specific terms: "vpc" better than "network", "kubernetes" better than "container"

    Args:
        query: Specific search term (e.g., "vpc", "kubernetes", "security")
        limit: Maximum results based on use case (optional only use if asked)

    Returns:
        JSON formatted module search results with download counts, descriptions, and verification status
    """
    start_time = time.time()

    try:
        # Validate request
        request = ModuleSearchRequest(query=query, limit=limit)

        # Import here to avoid circular imports
        from .tools.search import search_modules_impl

        # Execute search
        response = await search_modules_impl(request, config)

        # Log successful execution
        duration_ms = (time.time() - start_time) * 1000
        log_tool_execution(
            logger,
            "search_modules",
            request.model_dump(),
            duration_ms,
            success=True,
        )

        return response.model_dump_json(indent=2)

    except ValidationError as e:
        duration_ms = (time.time() - start_time) * 1000
        log_tool_execution(
            logger,
            "search_modules",
            {
                "query": query,
                "limit": limit,
            },
            duration_ms,
            success=False,
            error="validation_error",
        )
        raise TIMValidationError(f"Invalid parameters: {e}") from e

    except TIMError:
        duration_ms = (time.time() - start_time) * 1000
        log_tool_execution(
            logger,
            "search_modules",
            {
                "query": query,
                "limit": limit,
            },
            duration_ms,
            success=False,
        )
        raise

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_tool_execution(
            logger,
            "search_modules",
            {
                "query": query,
                "limit": limit,
            },
            duration_ms,
            success=False,
            error=str(e),
        )
        logger.exception("Unexpected error in search_modules")
        raise TIMError(f"Unexpected error: {e}") from e


@mcp.tool()
async def get_module_details(module_id: str) -> str:
    """
    Get structured module metadata from Terraform Registry - for understanding module interface when writing NEW terraform.

    WHEN TO USE (Development workflow only):
    - When user needs to CREATE/BUILD new terraform configurations
    - To understand required inputs/outputs for custom implementations
    - To check compatibility and requirements before development
    - When user asks about "inputs", "outputs", "parameters", "interface"

    WHEN NOT TO USE:
    - Skip this when user wants examples/samples (use list_content → get_content instead)
    - Skip when existing examples are available - prefer actual working code

    WHAT THIS PROVIDES:
    - Module description and documentation
    - Required inputs (variables) with types and descriptions
    - Available outputs with descriptions
    - Provider requirements and version constraints
    - Module dependencies

    Args:
        module_id: Full module identifier (e.g., "terraform-ibm-modules/vpc/ibm" or "terraform-ibm-modules/vpc/ibm/1.2.3")

    Returns:
        Plain text with markdown formatted module details including inputs, outputs, and description
    """
    start_time = time.time()

    try:
        # Validate request
        request = ModuleDetailsRequest(module_id=module_id)

        # Import here to avoid circular imports
        from .tools.details import get_module_details_impl

        # Execute details retrieval
        response = await get_module_details_impl(request, config)

        # Log successful execution
        duration_ms = (time.time() - start_time) * 1000
        log_tool_execution(
            logger,
            "get_module_details",
            request.model_dump(),
            duration_ms,
            success=True,
        )

        return response

    except ValidationError as e:
        duration_ms = (time.time() - start_time) * 1000
        log_tool_execution(
            logger,
            "get_module_details",
            {"module_id": module_id},
            duration_ms,
            success=False,
            error="validation_error",
        )
        raise TIMValidationError(f"Invalid parameters: {e}") from e

    except TIMError:
        duration_ms = (time.time() - start_time) * 1000
        log_tool_execution(
            logger,
            "get_module_details",
            {"module_id": module_id},
            duration_ms,
            success=False,
        )
        raise

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_tool_execution(
            logger,
            "get_module_details",
            {"module_id": module_id},
            duration_ms,
            success=False,
            error=str(e),
        )
        logger.exception("Unexpected error in get_module_details")
        raise TIMError(f"Unexpected error: {e}") from e


@mcp.tool()
async def list_content(module_id: str) -> str:
    """
    Discover available examples and repository structure - FIRST step in examples workflow.

    PRIMARY USE CASE (Examples workflow):
    - Check what examples/samples are available before fetching content
    - When user wants "examples", "samples", "deployment patterns"
    - Essential step before get_content to find the right example path

    SECONDARY USE CASE (Development workflow):
    - Explore repository structure during development
    - Find specific submodules or solutions

    CONTENT CATEGORIES:
    - Examples: Deployable examples showing module usage (PRIMARY TARGET for samples)
    - Solutions: Complete architecture patterns
    - Root Module: Main terraform files (for development)
    - Submodules: Reusable components (for advanced development)

    EXAMPLE SELECTION STRATEGY:
    - examples/basic or examples/simple → for straightforward demos
    - examples/complete → for comprehensive usage
    - solutions/ → for complex architecture patterns
    - Use descriptions to select the single most relevant example

    Args:
        module_id: Full module identifier (e.g., "terraform-ibm-modules/vpc/ibm" or "terraform-ibm-modules/vpc/ibm/1.2.3")

    Returns:
        Plain text with markdown formatted content listing organized by category
    """
    start_time = time.time()

    try:
        # Validate request
        request = ListContentRequest(module_id=module_id)

        # Import here to avoid circular imports
        from .tools.list_content import list_content_impl

        # Execute content listing
        response = await list_content_impl(request, config)

        # Log successful execution
        duration_ms = (time.time() - start_time) * 1000
        log_tool_execution(
            logger,
            "list_content",
            request.model_dump(),
            duration_ms,
            success=True,
        )

        return response

    except ValidationError as e:
        duration_ms = (time.time() - start_time) * 1000
        log_tool_execution(
            logger,
            "list_content",
            {"module_id": module_id},
            duration_ms,
            success=False,
            error="validation_error",
        )
        raise TIMValidationError(f"Invalid parameters: {e}") from e

    except TIMError:
        duration_ms = (time.time() - start_time) * 1000
        log_tool_execution(
            logger,
            "list_content",
            {"module_id": module_id},
            duration_ms,
            success=False,
        )
        raise

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_tool_execution(
            logger,
            "list_content",
            {"module_id": module_id},
            duration_ms,
            success=False,
            error=str(e),
        )
        logger.exception("Unexpected error in list_content")
        raise TIMError(f"Unexpected error: {e}") from e


@mcp.tool()
async def get_content(
    module_id: str,
    path: str = "",
    include_files: str | list[str] | None = None,
    exclude_files: str | list[str] | None = None,
) -> str:
    """
    Retrieve source code, examples, solutions from GitHub repositories with glob pattern filtering.

    Common patterns:
    - All Terraform files: include_files=["*.tf"]
    - Specific files: include_files=["main.tf", "variables.tf"]
    - Documentation: include_files=["*.md"]
    - Examples: path="examples/basic", include_files=["*.tf"]

    Args:
        module_id: Full module identifier (e.g., "terraform-ibm-modules/vpc/ibm" or "terraform-ibm-modules/vpc/ibm/1.2.3")
        path: Specific path: "" (root), "examples/basic", "modules/vpc"
        include_files: Glob patterns for files to include (e.g., ["*.tf"], ["*.md"])
        exclude_files: Glob patterns for files to exclude (e.g., ["*test*"])

    Returns:
        Plain text with markdown formatted content
    """
    start_time = time.time()

    try:
        # Sanitize list parameters in case they're passed as JSON strings
        sanitized_include_files = _sanitize_list_parameter(
            include_files, "include_files"
        )
        sanitized_exclude_files = _sanitize_list_parameter(
            exclude_files, "exclude_files"
        )

        # Validate request
        request = GetContentRequest(
            module_id=module_id,
            path=path,
            include_files=sanitized_include_files,
            exclude_files=sanitized_exclude_files,
        )

        # Import here to avoid circular imports
        from .tools.get_content import get_content_impl

        # Execute content retrieval
        response = await get_content_impl(request, config)

        # Log successful execution
        duration_ms = (time.time() - start_time) * 1000
        log_tool_execution(
            logger,
            "get_content",
            request.model_dump(),
            duration_ms,
            success=True,
        )

        return response

    except ValidationError as e:
        duration_ms = (time.time() - start_time) * 1000
        log_tool_execution(
            logger,
            "get_content",
            {
                "module_id": module_id,
                "path": path,
                "include_files": include_files,
                "exclude_files": exclude_files,
            },
            duration_ms,
            success=False,
            error="validation_error",
        )
        raise TIMValidationError(f"Invalid parameters: {e}") from e

    except TIMError:
        duration_ms = (time.time() - start_time) * 1000
        log_tool_execution(
            logger,
            "get_content",
            {
                "module_id": module_id,
                "path": path,
                "include_files": include_files,
                "exclude_files": exclude_files,
            },
            duration_ms,
            success=False,
        )
        raise

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_tool_execution(
            logger,
            "get_content",
            {
                "module_id": module_id,
                "path": path,
                "include_files": include_files,
                "exclude_files": exclude_files,
            },
            duration_ms,
            success=False,
            error=str(e),
        )
        logger.exception("Unexpected error in get_content")
        raise TIMError(f"Unexpected error: {e}") from e


@mcp.tool()
async def search_providers(
    query: str | None = None,
    limit: int = 10,
    offset: int = 0,
) -> str:
    """
    Search Terraform Registry for allowlisted providers by name or keyword.

    ALLOWLISTED PROVIDERS:
    - HashiCorp utility providers:
      - hashicorp/time - Time-based resources
      - hashicorp/null - Null resources for triggers
      - hashicorp/local - Local file operations
      - hashicorp/kubernetes - Kubernetes resources
      - hashicorp/random - Random value generation
      - hashicorp/helm - Helm chart deployment
      - hashicorp/external - External data sources
    - Mastercard/restapi - REST API provider for filling IBM Cloud provider gaps
    - IBM-Cloud/ibm - Primary IBM Cloud provider

    These providers are recommended by TIM for use with Terraform IBM Modules.

    SEARCH TIPS:
    - Search by provider name: "kubernetes", "random", "ibmcloud"
    - Or omit query to list recent allowlisted providers
    - Results are sorted by download count (most popular first)
    - Only allowlisted providers will be returned

    Args:
        query: Optional search term to filter providers (e.g., "kubernetes", "random")
        limit: Maximum results to return (default: 10, max: 100)
        offset: Pagination offset for retrieving additional results (default: 0)

    Returns:
        JSON formatted provider search results with download counts, versions, and tier information
    """
    start_time = time.time()

    try:
        # Validate request
        request = ProviderSearchRequest(query=query, limit=limit, offset=offset)

        # Import here to avoid circular imports
        from .tools.search_providers import search_providers_impl

        # Execute search
        response = await search_providers_impl(request, config)

        # Log successful execution
        duration_ms = (time.time() - start_time) * 1000
        log_tool_execution(
            logger,
            "search_providers",
            request.model_dump(),
            duration_ms,
            success=True,
        )

        return response.model_dump_json(indent=2)

    except ValidationError as e:
        duration_ms = (time.time() - start_time) * 1000
        log_tool_execution(
            logger,
            "search_providers",
            {
                "query": query,
                "limit": limit,
                "offset": offset,
            },
            duration_ms,
            success=False,
            error="validation_error",
        )
        raise TIMValidationError(f"Invalid parameters: {e}") from e

    except TIMError:
        duration_ms = (time.time() - start_time) * 1000
        log_tool_execution(
            logger,
            "search_providers",
            {
                "query": query,
                "limit": limit,
                "offset": offset,
            },
            duration_ms,
            success=False,
        )
        raise

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_tool_execution(
            logger,
            "search_providers",
            {
                "query": query,
                "limit": limit,
                "offset": offset,
            },
            duration_ms,
            success=False,
            error=str(e),
        )
        logger.exception("Unexpected error in search_providers")
        raise TIMError(f"Unexpected error: {e}") from e


@mcp.tool()
async def get_provider_details(provider_id: str) -> str:
    """
    Get comprehensive provider information from Terraform Registry for allowlisted providers.

    ALLOWLISTED PROVIDERS:
    - HashiCorp utility providers (time, null, local, kubernetes, random, helm, external)
    - Mastercard/restapi - REST API provider ONLY for filling IBM Cloud provider gaps
    - IBM-Cloud/ibm - Primary provider for IBM Cloud resources

    PROVIDER USAGE PRIORITIES:
    1. PRIMARY: Use IBM Cloud provider (IBM-Cloud/ibm) for IBM Cloud resources
    2. SECONDARY: Use Mastercard/restapi provider ONLY to fill functionality gaps in IBM Cloud provider
    3. TERTIARY: Use HashiCorp utility providers for cross-platform needs (time, random, null, etc.)
    4. Use providers to stitch together TIM modules where necessary

    IMPORTANT: The restapi provider is supplementary - use it sparingly and only when IBM Cloud
    provider lacks specific functionality. Always prefer TIM modules and IBM Cloud provider first.

    WHEN TO USE:
    - To understand allowlisted provider capabilities and features
    - To check available versions and tier status
    - To get usage examples and configuration snippets
    - When planning Terraform infrastructure with TIM modules

    PROVIDER INFORMATION INCLUDES:
    - Provider description and tier (official, partner, community)
    - Latest version and complete version history
    - Download statistics and publication date
    - Source repository and documentation links
    - Ready-to-use Terraform configuration examples

    Args:
        provider_id: Provider identifier (e.g., "hashicorp/random", "IBM-Cloud/ibm", "Mastercard/restapi")

    Returns:
        Plain text with markdown formatted provider details including versions and usage examples
    """
    start_time = time.time()

    try:
        # Validate request
        request = ProviderDetailsRequest(provider_id=provider_id)

        # Import here to avoid circular imports
        from .tools.get_provider_details import get_provider_details_impl

        # Execute details retrieval
        response = await get_provider_details_impl(request, config)

        # Log successful execution
        duration_ms = (time.time() - start_time) * 1000
        log_tool_execution(
            logger,
            "get_provider_details",
            request.model_dump(),
            duration_ms,
            success=True,
        )

        return response

    except ValidationError as e:
        duration_ms = (time.time() - start_time) * 1000
        log_tool_execution(
            logger,
            "get_provider_details",
            {"provider_id": provider_id},
            duration_ms,
            success=False,
            error="validation_error",
        )
        raise TIMValidationError(f"Invalid parameters: {e}") from e

    except TIMError:
        duration_ms = (time.time() - start_time) * 1000
        log_tool_execution(
            logger,
            "get_provider_details",
            {"provider_id": provider_id},
            duration_ms,
            success=False,
        )
        raise

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_tool_execution(
            logger,
            "get_provider_details",
            {"provider_id": provider_id},
            duration_ms,
            success=False,
            error=str(e),
        )
        logger.exception("Unexpected error in get_provider_details")
        raise TIMError(f"Unexpected error: {e}") from e


def main(transport_config=None):
    """
    Run the MCP server with specified transport configuration.

    Args:
        transport_config: Transport configuration (None = default STDIO)
    """
    logger.info("Starting TIM-MCP server", config=config.model_dump())

    if transport_config is None:
        # Default STDIO mode
        mcp.run()
    elif transport_config.mode == "stdio":
        # Explicit STDIO mode
        mcp.run()
    elif transport_config.mode == "http":
        # HTTP mode with specified host and port (always stateless)
        logger.info(
            f"Starting stateless HTTP server on {transport_config.host}:{transport_config.port}"
        )
        mcp.run(
            transport="http",
            host=transport_config.host,
            port=transport_config.port,
            stateless_http=True,
        )
    else:
        raise ValueError(f"Unsupported transport mode: {transport_config.mode}")


if __name__ == "__main__":
    main()
