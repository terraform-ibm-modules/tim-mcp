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
    Search Terraform Registry for modules with IBM Cloud optimizations.

    Args:
        query: Search term (e.g., "vpc", "kubernetes", "security")
        namespace: Module publisher (e.g., "terraform-ibm-modules")
        provider: Primary provider filter (e.g., "ibm", "aws")
        limit: Maximum results to return (default: 10)

    Returns:
        JSON formatted module search results
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
    Get structured module metadata from Terraform Registry.

    Args:
        module_id: Full module identifier (e.g., "terraform-ibm-modules/vpc/ibm")
        version: Specific version or latest

    Returns:
        Plain text with markdown formatted module details
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
    Discover available paths in a module repository with README summaries.

    Searches and categorizes paths into: root module, examples/ directories,
    modules/ (submodules), and patterns/solutions/ directories.

    Args:
        module_id: Full module identifier (e.g., "terraform-ibm-modules/vpc/ibm")
        version: Git tag/branch to scan

    Returns:
        Plain text with markdown formatted content listing
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
    Retrieve source code, examples, solutions from GitHub repositories.

    Args:
        module_id: Full module identifier (e.g., "terraform-ibm-modules/vpc/ibm")
        path: Path to fetch: "" (root), "examples/basic", "modules/vpc", "solutions/pattern1"
        include_files: List of regex patterns to include files, e.g., [".*\\.tf$", "README\\.md$"] for Terraform files and README, or [".*"] for everything
        exclude_files: List of regex patterns to exclude files, e.g., [".*test.*", ".*\\.tftest$"] to exclude test files
        include_readme: Include README.md for context (default: true)
        version: Git tag/branch to fetch from

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
