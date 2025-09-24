"""
TIM-MCP Server.

This module implements the main MCP server using FastMCP with tools
for Terraform IBM Modules discovery and implementation support.
"""

import json
import time
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
)

# Global configuration and logger
config: Config = load_config()
configure_logging(config)
logger = get_logger(__name__)

# Initialize FastMCP server
mcp = FastMCP("TIM-MCP")


def _sanitize_list_parameter(param: Any, param_name: str) -> list[str] | None:
    """
    Sanitize list parameters that might be passed as JSON strings by LLMs.

    Args:
        param: The parameter value to sanitize
        param_name: Name of the parameter for logging

    Returns:
        Sanitized list or None

    Raises:
        ValueError: If the parameter cannot be converted to a proper format
    """
    if param is None:
        return None

    if isinstance(param, list):
        # Validate all items are strings
        if not all(isinstance(item, str) for item in param):
            raise ValueError(
                f"Parameter {param_name} must be a list of strings, None, or a JSON array string"
            )
        return param

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
                    return parsed
            except json.JSONDecodeError:
                pass

        # If it's a single string that's not JSON, convert to single-item list
        logger.warning(
            f"Parameter {param_name} was passed as string, converting to single-item list",
            original_value=param,
        )
        return [param]

    raise ValueError(
        f"Parameter {param_name} must be a list of strings, None, or a JSON array string"
    )


@mcp.tool()
async def search_modules(
    query: str,
    namespace: str | None = None,
    provider: str | None = None,
    limit: int = 10,
) -> str:
    """
    Search Terraform Registry for modules with intelligent result optimization for different scenarios.

    RESULT OPTIMIZATION BY USE CASE:
    - For SPECIFIC MODULE lookup: limit=3-5 (user knows what they want)
    - For EXPLORING OPTIONS: limit=10-15 (default, good balance)
    - For COMPREHENSIVE RESEARCH: limit=20+ (when user wants to compare many options)
    - For QUICK REFERENCE: limit=1-3 (when user just needs "a VPC module" or similar)

    SEARCH EFFICIENCY TIPS:
    - Use SPECIFIC terms: "vpc" better than "network", "kubernetes" better than "container"
    - Combine query + namespace for precise results: query="vpc", namespace="terraform-ibm-modules"
    - Use provider="ibm" to focus on IBM Cloud modules (this server specializes in IBM Cloud)
    - For broad exploration, start with popular terms: "vpc", "iks", "cos", "security"

    INTELLIGENT FILTERING:
    - namespace="terraform-ibm-modules" for official IBM modules (most reliable)
    - provider="ibm" narrows to IBM Cloud specific modules
    - Higher download counts typically indicate better maintained modules
    - "verified" status indicates official publisher verification

    WORKFLOW OPTIMIZATION:
    - Search -> pick ONE relevant module -> use get_module_details for overview -> use list_content for structure -> use get_content for specific needs
    - Don't search multiple times unless user explicitly wants to compare different approaches

    Args:
        query: Specific search term (e.g., "vpc", "kubernetes", "security") - be specific for better results
        namespace: Module publisher (e.g., "terraform-ibm-modules" for official IBM modules)
        provider: Primary provider filter (e.g., "ibm" for IBM Cloud)
        limit: Maximum results (3-5 for specific lookup, 10+ for exploration, 20+ for research)

    Returns:
        JSON formatted module search results with download counts, descriptions, and verification status
    """
    start_time = time.time()

    try:
        # Validate request
        request = ModuleSearchRequest(
            query=query, namespace=namespace, provider=provider, limit=limit
        )

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
                "namespace": namespace,
                "provider": provider,
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
                "namespace": namespace,
                "provider": provider,
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
                "namespace": namespace,
                "provider": provider,
                "limit": limit,
            },
            duration_ms,
            success=False,
            error=str(e),
        )
        logger.exception("Unexpected error in search_modules")
        raise TIMError(f"Unexpected error: {e}") from e


@mcp.tool()
async def get_module_details(module_id: str, version: str = "latest") -> str:
    """
    Get structured module metadata from Terraform Registry - use this for high-level overview before diving into code.

    WHEN TO USE THIS TOOL:
    - FIRST step after finding a module to understand its purpose and interface
    - When user needs INPUT/OUTPUT information without seeing actual code
    - To get module description, version info, and basic usage without fetching files
    - When you need to understand module capabilities before recommending examples
    - To check compatibility and requirements before showing implementation

    WHAT THIS PROVIDES:
    - Module description and documentation
    - Required inputs (variables) with types and descriptions
    - Available outputs with descriptions
    - Provider requirements and versions
    - Module dependencies and usage patterns
    - Latest version information

    WHEN TO PROCEED TO OTHER TOOLS:
    - If this provides sufficient info for user's question → STOP HERE (avoid unnecessary content fetching)
    - If user needs to see actual code → use get_content with specific filters
    - If user wants to explore examples → use list_content then get_content
    - If user needs implementation details → use get_content with targeted patterns

    EFFICIENCY TIPS:
    - This tool provides structured metadata without heavy file downloads
    - Use this to answer questions about "what inputs does this module need" or "what outputs are available"
    - Sufficient for understanding module interface before implementation
    - Much lighter than fetching actual source files

    Args:
        module_id: Full module identifier (e.g., "terraform-ibm-modules/vpc/ibm")
        version: Specific version or "latest" for most recent (default: "latest")

    Returns:
        Plain text with markdown formatted module details including inputs, outputs, and description
    """
    start_time = time.time()

    try:
        # Validate request
        request = ModuleDetailsRequest(module_id=module_id, version=version)

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
            {"module_id": module_id, "version": version},
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
            {"module_id": module_id, "version": version},
            duration_ms,
            success=False,
        )
        raise

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_tool_execution(
            logger,
            "get_module_details",
            {"module_id": module_id, "version": version},
            duration_ms,
            success=False,
            error=str(e),
        )
        logger.exception("Unexpected error in get_module_details")
        raise TIMError(f"Unexpected error: {e}") from e


@mcp.tool()
async def list_content(module_id: str, version: str = "latest") -> str:
    """
    Discover available paths in a module repository with README summaries - use this to optimize subsequent get_content calls.

    WHEN TO USE THIS TOOL:
    - BEFORE calling get_content to understand repository structure
    - When user asks "what examples are available" or "show me all options"
    - To find the RIGHT path for specific use cases (basic vs advanced examples)
    - When you need to recommend the most appropriate example to the user

    INTELLIGENT WORKFLOW:
    1. Call list_content first to see all available paths and their descriptions
    2. Based on user intent, select the MOST RELEVANT single path
    3. Use get_content with specific path and minimal file filters
    4. For "basic example" requests: choose examples/basic or examples/simple
    5. For "advanced usage" requests: choose examples/complete or solutions/

    CONTENT CATEGORIES EXPLAINED:
    - Root Module: Main terraform files, inputs/outputs definitions
    - Examples: Deployable examples showing how to use the module (START HERE for demos)
    - Submodules: Reusable components within the module (for advanced use)
    - Solutions: Complete architecture patterns using the module (for complex scenarios)

    OPTIMIZATION TIPS:
    - Use descriptions to pick the SINGLE best example instead of fetching all
    - Prioritize examples/basic for simple demonstrations
    - Use examples/complete for comprehensive usage
    - Choose solutions/ only when user needs full architecture patterns

    Args:
        module_id: Full module identifier (e.g., "terraform-ibm-modules/vpc/ibm")
        version: Git tag/branch to scan (default: "latest")

    Returns:
        Plain text with markdown formatted content listing organized by category
    """
    start_time = time.time()

    try:
        # Validate request
        request = ListContentRequest(module_id=module_id, version=version)

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
            {"module_id": module_id, "version": version},
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
            {"module_id": module_id, "version": version},
            duration_ms,
            success=False,
        )
        raise

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_tool_execution(
            logger,
            "list_content",
            {"module_id": module_id, "version": version},
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
    include_files: list[str] | None = None,
    exclude_files: list[str] | None = None,
    include_readme: bool = True,
    version: str = "latest",
) -> str:
    """
    Retrieve source code, examples, solutions from GitHub repositories with intelligent content filtering.

    CONTEXT-AWARE USAGE GUIDANCE:
    - For INPUT VARIABLES only: include_files=["variables\\.tf$"], include_readme=false
    - For OUTPUT VALUES only: include_files=["outputs\\.tf$"], include_readme=false
    - For BASIC EXAMPLES only: path="examples/basic", include_files=["main\\.tf$", "variables\\.tf$"], exclude_files=[".*test.*"]
    - For MODULE STRUCTURE only: include_files=["main\\.tf$"], include_readme=true
    - For COMPLETE EXAMPLE: path="examples/{name}", include_files=[".*\\.tf$"], exclude_files=[".*test.*", ".*\\.tftest$"]
    - For ROOT MODULE: path="", include_files=["main\\.tf$", "variables\\.tf$", "outputs\\.tf$"]

    INTELLIGENT FILTERING:
    - Use specific patterns to avoid large responses. Avoid [".*"] unless you need everything
    - Common patterns: [".*\\.tf$"] (Terraform files), [".*\\.md$"] (docs), ["main\\.tf$"] (entry point only)
    - Exclude tests by default: exclude_files=[".*test.*", ".*\\.tftest$", ".*_test\\..*"]
    - For minimal examples, request 1 example path rather than all examples

    FALLBACK STRATEGY:
    - If specific files not found (e.g., no variables.tf), tool will return available files
    - Use list_content first to discover what's available in the repository
    - Start specific, then broaden scope if needed

    Args:
        module_id: Full module identifier (e.g., "terraform-ibm-modules/vpc/ibm")
        path: Specific path to fetch: "" (root), "examples/basic", "modules/vpc", "solutions/pattern1"
        include_files: Regex patterns for files to include. BE SPECIFIC - avoid [".*"] for large repos
        exclude_files: Regex patterns for files to exclude (tests, irrelevant files)
        include_readme: Include README.md for context. Set false when you only need code
        version: Git tag/branch to fetch from (default: "latest")

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
            include_readme=include_readme,
            version=version,
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
                "include_readme": include_readme,
                "version": version,
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
                "include_readme": include_readme,
                "version": version,
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
                "include_readme": include_readme,
                "version": version,
            },
            duration_ms,
            success=False,
            error=str(e),
        )
        logger.exception("Unexpected error in get_content")
        raise TIMError(f"Unexpected error: {e}") from e


def main():
    """Run the MCP server."""
    logger.info("Starting TIM-MCP server", config=config.model_dump())
    mcp.run()


if __name__ == "__main__":
    main()
