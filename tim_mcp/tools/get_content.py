"""
Implementation of the get_content tool for TIM-MCP.

This module provides functionality to fetch and format repository content
from GitHub, including source code, examples, and documentation with
comprehensive filtering capabilities.
"""

import asyncio
import re
from typing import Any

from ..clients.github_client import GitHubClient
from ..config import Config
from ..logging import get_logger
from ..types import GetContentRequest
from ..utils.module_id import parse_module_id_with_version, transform_version_for_github

logger = get_logger(__name__)


async def get_content_impl(
    request: GetContentRequest,
    config: Config,
    github_client: GitHubClient | None = None,
) -> str:
    """
    Implementation function for the get_content tool.

    Args:
        request: GetContentRequest with module_id, path, and filtering options
        config: Configuration instance
        github_client: Optional GitHub client instance for testing

    Returns:
        Formatted markdown string with repository content

    Raises:
        ModuleNotFoundError: If module or path not found
        GitHubError: If GitHub API request fails
    """
    if github_client is None:
        async with GitHubClient(config) as github_client:
            return await _get_content_with_client(request, github_client)
    else:
        return await _get_content_with_client(request, github_client)


async def _get_content_with_client(
    request: GetContentRequest, github_client: GitHubClient
) -> str:
    """
    Internal function to get content with a provided GitHub client.

    Args:
        request: GetContentRequest with module_id (may include version), path, and filtering options
        github_client: GitHub client instance

    Returns:
        Formatted markdown string with repository content
    """
    # Parse module ID to extract version if included
    namespace, name, provider, version = parse_module_id_with_version(request.module_id)
    base_module_id = f"{namespace}/{name}/{provider}"
    
    # Extract repository information
    owner, repo = github_client._extract_repo_from_module_id(base_module_id)

    # Transform version for GitHub tag lookup (add "v" prefix if needed)
    github_version = transform_version_for_github(version)

    # Resolve version to actual git reference
    resolved_version = await github_client.resolve_version(owner, repo, github_version)

    logger.info(
        "Fetching content for module",
        module_id=base_module_id,
        owner=owner,
        repo=repo,
        path=request.path,
        version=version,
        resolved_version=resolved_version,
    )

    # Get directory contents
    directory_contents = await github_client.get_directory_contents(
        owner, repo, request.path, resolved_version
    )

    # Filter files based on patterns
    filtered_files = _filter_files(
        directory_contents, github_client, request.include_files, request.exclude_files
    )

    logger.info(
        "Filtered files for content fetch",
        total_files=len(directory_contents),
        filtered_files=len(filtered_files),
        include_patterns=request.include_files,
        exclude_patterns=request.exclude_files,
    )

    # Prepare file fetch tasks
    fetch_tasks = []
    for file_item in filtered_files:
        task = github_client.get_file_content(
            owner, repo, file_item["path"], resolved_version
        )
        fetch_tasks.append(task)

    # Fetch all content concurrently
    results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

    # Process file results
    file_contents = []
    for i, file_item in enumerate(filtered_files):
        result = results[i]
        if not isinstance(result, Exception):
            file_contents.append(
                {
                    "name": file_item["name"],
                    "path": file_item["path"],
                    "content": result.get("decoded_content", ""),
                    "size": result.get("size", 0),
                }
            )
        else:
            # Log file fetch error but continue processing other files
            logger.warning(
                "Failed to fetch file content",
                file_path=file_item["path"],
                error=str(result),
            )

    logger.info(
        "Content fetch completed",
        files_fetched=len(file_contents),
        files_failed=len(filtered_files) - len(file_contents),
    )

    # Format the output
    return _format_content_output(
        base_module_id, request.path, resolved_version, file_contents
    )


def _format_content_output(
    module_id: str,
    path: str,
    version: str,
    file_contents: list[dict[str, Any]],
) -> str:
    """
    Format the content output as markdown.

    Args:
        module_id: Module identifier
        path: Path that was fetched
        version: Version that was fetched
        file_contents: List of file content data

    Returns:
        Formatted markdown string
    """
    # Build title
    title_parts = [module_id]
    if path:
        title_parts.append(path)
    title = f"# {' - '.join(title_parts)}"

    # Build header
    lines = [title, "", f"**Version:** {version}", ""]

    if not file_contents:
        lines.append("No files found matching the specified criteria.")
    else:
        # Sort files for consistent output - put README first if present
        def sort_key(file_data):
            name = file_data["name"]
            if name.upper() == "README.MD":
                return "0_" + name  # Sort README first
            return name

        sorted_files = sorted(file_contents, key=sort_key)

        for file_data in sorted_files:
            file_extension = file_data["name"].split(".")[-1].lower()

            # Choose appropriate syntax highlighting
            if file_extension in ["tf", "hcl"]:
                syntax = "terraform"
            elif file_extension in ["md", "markdown"]:
                syntax = "markdown"
            elif file_extension in ["yaml", "yml"]:
                syntax = "yaml"
            elif file_extension in ["json"]:
                syntax = "json"
            else:
                syntax = "text"

            lines.extend(
                [
                    f"## {file_data['name']}",
                    f"```{syntax}",
                    file_data["content"].strip(),
                    "```",
                    "",
                ]
            )

    # Add configuration summary if we have terraform files
    if file_contents and _has_terraform_config_files(file_contents):
        summary = _generate_config_summary(file_contents)
        lines.extend(["## Configuration Summary", "", summary])

    return "\n".join(lines)


def _has_terraform_config_files(file_contents: list[dict[str, Any]]) -> bool:
    """
    Check if the file contents include terraform configuration files.

    Args:
        file_contents: List of file content data

    Returns:
        True if terraform config files are present
    """
    config_files = {"variables.tf", "outputs.tf", "main.tf"}
    file_names = {file_data["name"] for file_data in file_contents}
    return len(config_files.intersection(file_names)) > 0


def _filter_files(
    directory_contents: list[dict[str, Any]],
    github_client: GitHubClient,
    include_patterns: list[str] | None,
    exclude_patterns: list[str] | None,
) -> list[dict[str, Any]]:
    """
    Filter files based on include/exclude patterns.

    Args:
        directory_contents: List of directory items from GitHub API
        github_client: GitHub client for pattern matching
        include_patterns: List of glob patterns to include
        exclude_patterns: List of glob patterns to exclude

    Returns:
        List of filtered file items
    """
    filtered_files = []
    for item in directory_contents:
        if item.get("type") == "file":
            file_path = item["path"]
            if github_client.match_file_patterns(
                file_path, include_patterns, exclude_patterns
            ):
                filtered_files.append(item)
    return filtered_files


def _generate_config_summary(file_contents: list[dict[str, Any]]) -> str:
    """
    Generate a configuration summary from terraform files.

    Args:
        file_contents: List of file content data

    Returns:
        Configuration summary string
    """
    inputs = []
    outputs = []
    dependencies = []

    for file_data in file_contents:
        content = file_data["content"]
        filename = file_data["name"]

        # Extract variables
        if filename == "variables.tf":
            var_matches = re.findall(r'variable\s+"([^"]+)"', content)
            inputs.extend(var_matches)

        # Extract outputs
        if filename == "outputs.tf":
            output_matches = re.findall(r'output\s+"([^"]+)"', content)
            outputs.extend(output_matches)

        # Extract module dependencies from main.tf
        if filename == "main.tf":
            module_matches = re.findall(r'module\s+"([^"]+)"', content)
            dependencies.extend(module_matches)

    summary_lines = []

    if inputs:
        summary_lines.append(f"**Required Inputs:** {', '.join(sorted(set(inputs)))}")

    if outputs:
        summary_lines.append(f"**Outputs:** {', '.join(sorted(set(outputs)))}")

    if dependencies:
        summary_lines.append(
            f"**Dependencies:** {', '.join(sorted(set(dependencies)))}"
        )
    else:
        summary_lines.append("**Dependencies:** None")

    if not inputs and not outputs:
        summary_lines = ["**Configuration:** No variables or outputs detected"]

    return "  \n".join(summary_lines)
