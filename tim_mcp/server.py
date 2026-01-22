"""
TIM-MCP Server.

This module implements the main MCP server using FastMCP with tools
for Terraform IBM Modules discovery and implementation support.
"""

import json
import textwrap
import time
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from pydantic import ValidationError

from .config import Config, load_config
from .context import init_context
from .exceptions import TIMError
from .exceptions import ValidationError as TIMValidationError
from .logging import configure_logging, get_logger, log_tool_execution
from .types import (
    GetContentRequest,
    ListContentRequest,
    ModuleDetailsRequest,
    ModuleSearchRequest,
)
from .utils.cache import InMemoryCache
from .utils.rate_limiter import RateLimiter

# Global configuration and logger
config: Config = load_config()
configure_logging(config)
logger = get_logger(__name__)

# Initialize global rate limiter and shared cache
global_rate_limiter = RateLimiter(
    max_requests=config.global_rate_limit,
    window_seconds=config.rate_limit_window,
)

shared_cache = InMemoryCache(
    ttl=config.cache_ttl,
    maxsize=config.cache_maxsize,
)

# Initialize shared context for tools
init_context(global_rate_limiter, shared_cache)

logger.info(
    "Rate limiter and cache initialized",
    global_rate_limit=config.global_rate_limit,
    rate_limit_window=config.rate_limit_window,
    cache_ttl=config.cache_ttl,
    cache_maxsize=config.cache_maxsize,
)


def _find_static_file(filename: str) -> Path:
    """
    Find a file in the static directory, checking both packaged and development locations.

    Args:
        filename: Name of the file to find in the static directory

    Returns:
        Path object to the found file

    Raises:
        FileNotFoundError: If the file cannot be found in either location
    """
    # First try the packaged location (when installed via pip/uvx)
    packaged_path = Path(__file__).parent / "static" / filename
    # Then try the development location (when running from source)
    dev_path = Path(__file__).parent.parent / "static" / filename

    for file_path in [packaged_path, dev_path]:
        if file_path.exists():
            return file_path

    # If neither path works, provide helpful error message
    logger.error(f"File not found at {packaged_path} or {dev_path}")
    raise FileNotFoundError(
        f"Required file '{filename}' not found. Searched locations:\n"
        f"  - {packaged_path} (packaged installation)\n"
        f"  - {dev_path} (development installation)\n"
        f"Please ensure the file exists in the static directory."
    )


def _load_instructions() -> str:
    """Load instructions from the static instructions file."""
    try:
        instructions_path = _find_static_file("instructions.md")
        return instructions_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"Error reading instructions file: {e}")
        raise


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


@mcp.resource(
    uri="whitepaper://terraform-best-practices-on-ibm-cloud",
    name="IBM Terraform Whitepaper",
    description=textwrap.dedent("""
    A concise guide to best practices for designing, coding, securing, and operating Terraform Infrastructure as Code solutions on IBM Cloud.
    Focuses on modularity, deployable architectures, security governance, and operational workflows.
    """),
    mime_type="text/markdown",
    tags={"documentation", "best-practices", "terraform"},
    meta={
        "version": "1.0",
        "team": "IBM Cloud",
        "update_frequency": "monthly",
        "file_size_bytes": _find_static_file("terraform-white-paper.md").stat().st_size,
    },
)
async def terraform_whitepaper():
    whitepaper_path = _find_static_file("terraform-white-paper.md")
    return whitepaper_path.read_text(encoding="utf-8")


@mcp.resource(
    uri="catalog://terraform-ibm-modules-index",
    name="IBM Terraform Modules Index",
    description=textwrap.dedent("""
    IBM Terraform Modules Index - A comprehensive list of all IBM Terraform modules.

    This resource provides a curated index of IBM Terraform modules from the
    terraform-ibm-modules namespace, including:
    - Module ID, name, namespace, and provider
    - Description and category
    - Download count (modules are sorted by popularity)
    - Published date
    - Source URL on GitHub

    The index is filtered to include only:
    - Modules published in the last 3 months
    - Modules from the terraform-ibm-modules GitHub organization

    Use this resource to get an overview of available modules for context enrichment.
    For detailed module information (inputs, outputs, etc.), use the get_module_details tool.
    """),
    mime_type="application/json",
    tags={"index", "modules", "terraform"},
    meta={
        "version": "1.0",
        "team": "IBM Cloud",
        "update_frequency": "weekly",
        "file_size_bytes": _find_static_file("module_index.json").stat().st_size,
    },
)
async def module_index():
    try:
        module_index_path = _find_static_file("module_index.json")
        return module_index_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("Module index not found, returning empty index")
        return json.dumps(
            {
                "generated_at": None,
                "total_modules": 0,
                "namespace": "terraform-ibm-modules",
                "modules": [],
                "note": "Index not yet generated. Run scripts/generate_module_index.py",
            },
            indent=2,
        )


def get_stats() -> dict:
    """Get cache and rate limiter statistics."""
    return {
        "cache": shared_cache.get_stats(),
        "rate_limiter": {
            "global": global_rate_limiter.get_stats("global"),
            "config": {
                "max_requests": global_rate_limiter.max_requests,
                "window_seconds": global_rate_limiter.window_seconds,
            },
        },
    }


def main(transport_config=None):
    """
    Run the MCP server with specified transport configuration.

    Args:
        transport_config: Transport configuration (None = default STDIO)
    """
    logger.info("Starting TIM-MCP server", config=config.model_dump())

    if transport_config is None:
        # Default STDIO mode
        mcp.run(show_banner=False)
    elif transport_config.mode == "stdio":
        # Explicit STDIO mode
        mcp.run(show_banner=False)
    elif transport_config.mode == "http":
        # HTTP mode with specified host and port (always stateless)
        logger.info(
            f"Starting stateless HTTP server on {transport_config.host}:{transport_config.port}"
        )

        # Add per-IP rate limiting middleware for HTTP mode
        import uvicorn
        from starlette.middleware import Middleware
        from starlette.responses import JSONResponse
        from starlette.routing import Route

        from .middleware import PerIPRateLimitMiddleware

        per_ip_limiter = RateLimiter(
            max_requests=config.per_ip_rate_limit,
            window_seconds=config.rate_limit_window,
        )

        # Get the app with middleware applied
        app = mcp.http_app(
            stateless_http=True,
            middleware=[
                Middleware(
                    PerIPRateLimitMiddleware,
                    rate_limiter=per_ip_limiter,
                    bypass_paths=["/health", "/stats"],
                )
            ],
        )

        # Add stats endpoints
        async def stats_endpoint(request):
            """Return cache and rate limiter statistics."""
            stats = get_stats()
            stats["rate_limiter"]["per_ip"] = {
                "config": {
                    "max_requests": per_ip_limiter.max_requests,
                    "window_seconds": per_ip_limiter.window_seconds,
                }
            }
            return JSONResponse(stats)

        async def cache_stats_endpoint(request):
            """Return detailed cache statistics."""
            top = int(request.query_params.get("top", 20))
            return JSONResponse(shared_cache.get_detailed_stats(top=top))

        app.routes.append(Route("/stats", stats_endpoint, methods=["GET"]))
        app.routes.append(Route("/stats/cache", cache_stats_endpoint, methods=["GET"]))

        logger.info(
            "Per-IP rate limiting enabled",
            per_ip_rate_limit=config.per_ip_rate_limit,
            rate_limit_window=config.rate_limit_window,
        )

        # Run with uvicorn directly to use our configured app
        uvicorn.run(
            app,
            host=transport_config.host,
            port=transport_config.port,
        )
    else:
        raise ValueError(f"Unsupported transport mode: {transport_config.mode}")


if __name__ == "__main__":
    main()
