"""
Module dependency suggestions tool implementation for TIM-MCP.

This module provides functionality to suggest module dependencies by reading
mappings.hcl from a Git repository at a given reference (branch/tag/commit).
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

import hcl2

from ..config import Config
from ..exceptions import TIMError, ValidationError
from ..logging import get_logger
from ..types import (
    ModuleDependencySuggestion,
    SuggestModuleDependenciesRequest,
    SuggestModuleDependenciesResponse,
)

logger = get_logger(__name__)


class GitOperationError(TIMError):
    """Error during Git operations."""

    def __init__(self, message: str, details: str | None = None):
        super().__init__(message)
        self.details = details


class MappingsFileError(TIMError):
    """Error reading or parsing mappings.hcl file."""

    def __init__(self, message: str, details: str | None = None):
        super().__init__(message)
        self.details = details


def _clone_repository(repo_url: str, target_dir: str) -> None:
    """
    Clone a Git repository to a target directory.

    Args:
        repo_url: Git repository URL
        target_dir: Target directory for cloning

    Raises:
        GitOperationError: If cloning fails
    """
    try:
        subprocess.run(
            ["git", "clone", "--quiet", repo_url, target_dir],
            check=True,
            capture_output=True,
            text=True,
        )
        logger.info("Repository cloned successfully", repo_url=repo_url)
    except subprocess.CalledProcessError as e:
        raise GitOperationError(
            f"Failed to clone repository: {repo_url}",
            details=e.stderr.strip() if e.stderr else str(e),
        ) from e


def _fetch_ref(repo_path: str, ref: str) -> None:
    """
    Fetch a specific Git reference.

    Args:
        repo_path: Path to the Git repository
        ref: Git reference (branch, tag, or commit)

    Raises:
        GitOperationError: If fetching fails
    """
    try:
        subprocess.run(
            ["git", "-C", repo_path, "fetch", "origin", ref],
            check=True,
            capture_output=True,
            text=True,
        )
        logger.info("Git reference fetched successfully", ref=ref)
    except subprocess.CalledProcessError as e:
        raise GitOperationError(
            f"Failed to fetch reference: {ref}",
            details=e.stderr.strip() if e.stderr else str(e),
        ) from e


def _read_mappings_file(repo_path: str, ref: str) -> dict:
    """
    Read mappings.hcl from a specific Git reference.

    Args:
        repo_path: Path to the Git repository
        ref: Git reference (branch, tag, or commit)

    Returns:
        Parsed HCL data from mappings.hcl

    Raises:
        MappingsFileError: If reading or parsing fails
    """
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "show", f"origin/{ref}:mappings.hcl"],
            capture_output=True,
            text=True,
            check=True,
        )
        logger.info("mappings.hcl retrieved successfully", ref=ref)
        return hcl2.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        raise MappingsFileError(
            f"Unable to retrieve mappings.hcl at ref '{ref}'",
            details=e.stderr.strip() if e.stderr else str(e),
        ) from e
    except Exception as e:
        raise MappingsFileError(
            "Invalid HCL in mappings.hcl",
            details=str(e),
        ) from e


def _parse_dependencies(mappings_data: dict) -> list[ModuleDependencySuggestion]:
    """
    Parse module dependencies from mappings.hcl data.

    Args:
        mappings_data: Parsed HCL data from mappings.hcl

    Returns:
        List of module dependency suggestions
    """
    # HCL2 parser returns lists for blocks, so we need to handle that
    compatible_variables = mappings_data.get("compatible_variables", [])
    
    dependencies = []
    
    # If compatible_variables is a list (HCL blocks), take the first one
    if isinstance(compatible_variables, list) and compatible_variables:
        compatible_variables = compatible_variables[0]
    
    # Parse the compatible_variables mapping
    if isinstance(compatible_variables, dict):
        for target_input, source_output in compatible_variables.items():
            # Parse the format: "input_name" = "source_module.output.output_name"
            if not isinstance(source_output, str):
                logger.warning(
                    "Invalid source output format",
                    target_input=target_input,
                    source_output_type=type(source_output).__name__,
                )
                continue
            
            # The target_input is just the variable name (e.g., "resource_group_id")
            input_name = target_input
            
            # Extract module and output from source (e.g., "resource_group.output.resource_group_id")
            source_parts = source_output.split(".")
            if len(source_parts) < 3 or source_parts[1] != "output":
                logger.warning(
                    "Invalid source output format",
                    source_output=source_output,
                )
                continue
            
            source_module = source_parts[0]
            output_name = ".".join(source_parts[2:])  # Everything after "module.output."
            
            dependencies.append(
                ModuleDependencySuggestion(
                    source_module=source_module,
                    source_output=output_name,
                    target_input=input_name,
                )
            )

    return dependencies


async def suggest_module_dependencies_impl(
    request: SuggestModuleDependenciesRequest, config: Config
) -> SuggestModuleDependenciesResponse:
    """
    Implementation function for the suggest_module_dependencies MCP tool.

    This function reads mappings.hcl from a Git repository at a given reference
    and extracts module dependency suggestions.

    Args:
        request: The validated request containing module_path and ref
        config: Configuration instance (currently unused but kept for consistency)

    Returns:
        SuggestModuleDependenciesResponse containing dependency suggestions

    Raises:
        ValidationError: When parameters are invalid
        GitOperationError: When Git operations fail
        MappingsFileError: When mappings.hcl cannot be read or parsed
    """
    cleanup_dir = None
    repo_path = request.module_path

    try:
        # If module_path is a URL, clone it to a temporary directory
        if request.module_path.startswith(("http://", "https://", "git@")):
            cleanup_dir = tempfile.mkdtemp(prefix="tim-mcp-suggestions-")
            logger.info(
                "Cloning repository to temporary directory",
                repo_url=request.module_path,
                temp_dir=cleanup_dir,
            )
            _clone_repository(request.module_path, cleanup_dir)
            _fetch_ref(cleanup_dir, request.ref)
            repo_path = cleanup_dir
        else:
            # Local path - validate it exists
            local_path = Path(request.module_path)
            if not local_path.exists():
                raise ValidationError(
                    f"Local path does not exist: {request.module_path}"
                )
            if not (local_path / ".git").exists():
                raise ValidationError(
                    f"Path is not a Git repository: {request.module_path}"
                )
            logger.info("Using local repository", path=request.module_path)

        # Read and parse mappings.hcl
        mappings_data = _read_mappings_file(repo_path, request.ref)

        # Extract module information from metadata block
        metadata = mappings_data.get("metadata", [])
        if isinstance(metadata, list) and metadata:
            metadata = metadata[0]
        module_source = metadata.get("source") if isinstance(metadata, dict) else None

        # Parse dependencies
        dependencies = _parse_dependencies(mappings_data)

        logger.info(
            "Successfully parsed module dependencies",
            module=module_source,
            ref=request.ref,
            dependency_count=len(dependencies),
        )

        return SuggestModuleDependenciesResponse(
            module=module_source,
            ref=request.ref,
            required_dependencies=dependencies,
        )

    finally:
        # Clean up temporary directory if created
        if cleanup_dir:
            try:
                shutil.rmtree(cleanup_dir)
                logger.info("Cleaned up temporary directory", temp_dir=cleanup_dir)
            except Exception as e:
                logger.warning(
                    "Failed to clean up temporary directory",
                    temp_dir=cleanup_dir,
                    error=str(e),
                )

# Made with Bob
