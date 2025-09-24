"""
TIM-MCP Server.

This module implements the main MCP server using FastMCP with tools
for Terraform IBM Modules discovery and implementation support.
"""

import fnmatch
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
mcp = FastMCP(
    "TIM-MCP",
    instructions="""IBM Cloud Terraform module discovery and implementation server.

ARCHITECTURAL BEST PRACTICES:
- ALWAYS prefer terraform-ibm-modules over direct provider resources
- Common module alternatives:
  * Use 'resource-group' module instead of ibm_resource_group
  * Use 'cbr' modules instead of direct ibm_cbr_* resources
  * Use 'vpc' module instead of direct ibm_is_* resources
  * Use 'iks' or 'ocp' modules instead of direct cluster resources
- Modules provide security hardening, standardized configurations, and tested patterns
- Use direct provider resources only when no suitable module exists

STANDARD WORKFLOW:
1. search_modules → find relevant modules
2. get_module_details → understand module interface (often sufficient)
3. list_content → explore repository structure if needed
4. get_content → fetch specific implementation details
- Avoid multiple searches unless comparing approaches
- Stop at get_module_details if it provides sufficient information

OPTIMIZATION PRINCIPLES:
- Be specific in requests to minimize context usage and API calls
- Start with narrow scope (specific files/paths), broaden only if needed
- Exclude test files by default: [".*test.*", ".*\\.tftest$", ".*_test\\..*"]
- For examples, prefer single targeted example over fetching all examples

IBM CLOUD FOCUS:
- This server specializes in IBM Cloud modules and patterns
- Higher download counts indicate better maintained modules""",
)


def _is_glob_pattern(pattern: str) -> bool:
    """
    Check if a pattern looks like a glob pattern rather than a regex.

    Simple heuristics to detect glob patterns:
    - Contains * or ? without regex escaping
    - Looks like file extensions (*.ext)
    - Doesn't contain regex-specific characters like ^, $, [], etc.
    """
    # If it contains regex anchors or character classes, it's probably regex
    if any(char in pattern for char in ["^", "$", "[", "]", "\\."]):
        return False

    # If it contains glob wildcards, it's probably glob
    if any(char in pattern for char in ["*", "?"]):
        return True

    # If it looks like a simple filename, treat as glob
    if "." in pattern and not pattern.startswith("."):
        return True

    return False


def _convert_glob_to_regex(pattern: str) -> str:
    """
    Convert glob pattern to regex pattern.

    Uses fnmatch.translate which handles standard shell wildcards:
    - * matches everything
    - ? matches any single character
    - [seq] matches any character in seq
    - [!seq] matches any character not in seq
    """
    regex_pattern = fnmatch.translate(pattern)

    # fnmatch.translate output format: '(?s:PATTERN)\Z'
    # Clean these up for compatibility with our existing regex matching

    # Convert \Z (end of string) to $ for consistency first
    if regex_pattern.endswith("\\Z"):
        regex_pattern = regex_pattern[:-2] + "$"

    # Remove (?s:...) wrapper if present
    if regex_pattern.startswith("(?s:") and ")$" in regex_pattern:
        # Find the last )$ to properly handle nested groups
        close_pos = regex_pattern.rfind(")$")
        if close_pos > 4:
            inner_pattern = regex_pattern[4:close_pos]
            regex_pattern = inner_pattern + "$"
    elif regex_pattern.startswith("(?ms:") and ")$" in regex_pattern:
        close_pos = regex_pattern.rfind(")$")
        if close_pos > 5:
            inner_pattern = regex_pattern[5:close_pos]
            regex_pattern = inner_pattern + "$"

    return regex_pattern


def _sanitize_list_parameter(param: Any, param_name: str) -> list[str] | None:
    """
    Sanitize list parameters that might be passed as JSON strings by LLMs.

    This function handles common patterns and automatically converts glob patterns
    to regex patterns for easier use by LLMs. Examples:
    - "*.tf" becomes ".*\\.tf$"
    - ["*.tf", "*.md"] becomes [".*\\.tf$", ".*\\.md$"]

    Args:
        param: The parameter value to sanitize
        param_name: Name of the parameter for logging

    Returns:
        Sanitized list with glob patterns converted to regex or None

    Raises:
        ValueError: If the parameter cannot be converted to a proper format
    """
    if param is None:
        return None

    def _process_pattern_list(patterns: list[str]) -> list[str]:
        """Process a list of patterns, converting globs to regex as needed."""
        processed = []
        converted_any = False

        for pattern in patterns:
            if _is_glob_pattern(pattern):
                converted_pattern = _convert_glob_to_regex(pattern)
                processed.append(converted_pattern)
                converted_any = True
                logger.info(
                    f"Converted glob pattern to regex in {param_name}",
                    original=pattern,
                    converted=converted_pattern,
                )
            else:
                processed.append(pattern)

        if converted_any:
            logger.info(
                f"Auto-converted glob patterns to regex in {param_name}",
                original_patterns=patterns,
                converted_patterns=processed,
            )

        return processed

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
    limit: int = 10,
) -> str:
    """
    Search Terraform Registry for modules with intelligent result optimization.

    RESULT OPTIMIZATION BY USE CASE:
    - SPECIFIC MODULE lookup: limit=3-5 (user knows what they want)
    - EXPLORING OPTIONS: limit=10-15 (default, good balance)
    - COMPREHENSIVE RESEARCH: limit=20+ (when user wants to compare many options)
    - QUICK REFERENCE: limit=1-3 (when user just needs "a VPC module" or similar)

    SEARCH TIPS:
    - Use specific terms: "vpc" better than "network", "kubernetes" better than "container"

    Args:
        query: Specific search term (e.g., "vpc", "kubernetes", "security")
        limit: Maximum results based on use case (see optimization guidance above)

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
async def get_module_details(module_id: str, version: str = "latest") -> str:
    """
    Get structured module metadata from Terraform Registry - lightweight module interface overview.

    WHEN TO USE:
    - First step after finding a module to understand its interface
    - When you need input/output information without seeing code
    - To check compatibility and requirements
    - Often sufficient to answer user questions without fetching files

    WHAT THIS PROVIDES:
    - Module description and documentation
    - Required inputs (variables) with types and descriptions
    - Available outputs with descriptions
    - Provider requirements and version constraints
    - Module dependencies

    Args:
        module_id: Full module identifier (e.g., "terraform-ibm-modules/vpc/ibm")
        version: Specific version or "latest" (default: "latest")

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
    Discover available paths in a module repository with README summaries.

    WHEN TO USE:
    - Before calling get_content to understand repository structure
    - When user asks "what examples are available"
    - To find the right path for specific use cases

    CONTENT CATEGORIES:
    - Root Module: Main terraform files, inputs/outputs definitions
    - Examples: Deployable examples showing module usage (START HERE for demos)
    - Submodules: Reusable components within the module (for advanced use)
    - Solutions: Complete architecture patterns (for complex scenarios)

    USAGE TIPS:
    - For basic demonstrations: choose examples/basic or examples/simple
    - For comprehensive usage: choose examples/complete
    - For architecture patterns: choose solutions/
    - Use descriptions to select the single most relevant example

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
    include_files: str | list[str] | None = None,
    exclude_files: str | list[str] | None = None,
    include_readme: bool = True,
    version: str = "latest",
) -> str:
    """
    Retrieve source code, examples, solutions from GitHub repositories with targeted content filtering.

    SIMPLE FILE PATTERNS (Recommended - Easy to Use):
    - INPUT VARIABLES: include_files=["variables.tf"], include_readme=false
    - OUTPUT VALUES: include_files=["outputs.tf"], include_readme=false
    - BASIC EXAMPLES: path="examples/basic", include_files=["*.tf"]
    - MODULE STRUCTURE: include_files=["main.tf"], include_readme=true
    - ALL TERRAFORM FILES: include_files=["*.tf"]
    - DOCUMENTATION: include_files=["*.md"]
    - SPECIFIC FILE: include_files=["main.tf", "variables.tf"]

    USAGE PATTERNS BY GOAL:
    - Understand module inputs: include_files=["variables.tf"]
    - See module outputs: include_files=["outputs.tf"]
    - Get working example: path="examples/basic", include_files=["*.tf"]
    - Browse all terraform: include_files=["*.tf"]
    - Get documentation: include_files=["README.md", "*.md"]

    FILE PATTERN FORMATS (Both supported):
    - Simple patterns: ["*.tf", "*.md", "main.tf"] (Recommended)
    - Regex patterns: [".*\\.tf$", ".*\\.md$", "^main\\.tf$"] (Advanced)
    - Tool auto-converts simple patterns to regex internally

    PARAMETER FORMATS (Multiple formats supported):
    - List format (recommended): include_files=["*.tf", "*.md"]
    - JSON string format: include_files='["*.tf", "*.md"]'
    - Single string: include_files="*.tf"

    Args:
        module_id: Full module identifier (e.g., "terraform-ibm-modules/vpc/ibm")
        path: Specific path: "" (root), "examples/basic", "modules/vpc", "solutions/pattern1"
        include_files: File patterns (list, JSON string, or single string)
        exclude_files: File patterns (list, JSON string, or single string)
        include_readme: Include README.md for context (default: true)
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
