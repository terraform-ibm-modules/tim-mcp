"""
List content tool implementation for TIM-MCP.

This tool discovers available paths (examples, submodules, solutions) in a
module repository with README summaries to help users navigate the repository
structure and choose appropriate content for their needs.
"""

import re

from ..clients.github_client import GitHubClient
from ..config import Config
from ..exceptions import ModuleNotFoundError
from ..logging import get_logger
from ..types import ListContentRequest
from ..utils.cache import Cache

logger = get_logger(__name__)


async def list_content_impl(request: ListContentRequest, config: Config) -> str:
    """
    Implementation function for the list_content tool.

    Args:
        request: ListContentRequest with module_id and version
        config: Configuration instance

    Returns:
        Formatted string with available content paths and descriptions

    Raises:
        ModuleNotFoundError: If module repository is not found
        GitHubError: If GitHub API request fails
        RateLimitError: If GitHub rate limit is exceeded
    """
    # Extract repository information from module ID
    owner, repo_name = _extract_repo_from_module_id(request.module_id)

    # Initialize GitHub client
    cache = Cache(ttl=config.cache_ttl)
    github_client = GitHubClient(config, cache)

    try:
        # Get repository information
        await github_client.get_repository_info(owner, repo_name)

        # Resolve version to actual git reference
        resolved_version = await github_client.resolve_version(owner, repo_name, request.version)

        logger.info(
            "Listing content for module",
            module_id=request.module_id,
            owner=owner,
            repo=repo_name,
            version=request.version,
            resolved_version=resolved_version,
        )

        # Get repository tree structure
        tree_items = await github_client.get_repository_tree(owner, repo_name, resolved_version, recursive=True)

        # Categorize paths and collect README information
        categorized_paths = _categorize_tree_items(tree_items)

        # Extract README summaries for each significant path
        path_descriptions = await _extract_path_descriptions(github_client, owner, repo_name, resolved_version, categorized_paths)

        # Format output
        return _format_content_listing(request.module_id, resolved_version, categorized_paths, path_descriptions)
    finally:
        await github_client.client.aclose()


def _extract_repo_from_module_id(module_id: str) -> tuple[str, str]:
    """
    Extract GitHub repository owner and name from module ID.

    Args:
        module_id: Module ID in format "namespace/name/provider"

    Returns:
        Tuple of (owner, repo_name)

    Raises:
        ModuleNotFoundError: If module ID format is invalid
    """
    parts = module_id.split("/")
    if len(parts) != 3:
        raise ModuleNotFoundError(module_id, details={"reason": "Invalid module ID format"})

    namespace, name, provider = parts

    # For terraform-ibm-modules, the repo name is usually terraform-ibm-{name}
    if namespace == "terraform-ibm-modules":
        repo_name = f"terraform-ibm-{name}"
    else:
        # For other namespaces, try to construct the repo name
        repo_name = f"terraform-{name}-{provider}"

    return namespace, repo_name


def _categorize_tree_items(tree_items: list[dict]) -> dict[str, list[str]]:
    """
    Categorize tree items into different content types.

    Args:
        tree_items: List of tree items from GitHub API

    Returns:
        Dictionary mapping category names to lists of paths
    """
    categorized = {"root": [], "examples": [], "submodules": [], "solutions": []}

    # Track directories we've seen to avoid duplicates
    seen_dirs = set()

    for item in tree_items:
        if item["type"] == "tree":  # Only process directories
            path = item["path"]

            # Skip if we've already processed this directory
            if path in seen_dirs:
                continue
            seen_dirs.add(path)

            # Categorize the path
            category = _categorize_path(path)
            if category and category in categorized:
                categorized[category].append(path)

    # Root module is always present (represented by empty string)
    categorized["root"] = [""]

    return categorized


def _categorize_path(path: str) -> str | None:
    """
    Categorize a path into content type.

    This function classifies repository paths into logical categories
    based on common Terraform module conventions.

    Args:
        path: Directory path

    Returns:
        Category name or None if not categorized
    """
    path_lower = path.lower()

    # Examples directory
    if path_lower.startswith("examples/"):
        return "examples"

    # Submodules directory
    elif path_lower.startswith("modules/"):
        return "submodules"

    # Solutions/patterns directory
    elif path_lower.startswith(("patterns/", "solutions/")):
        return "solutions"

    # Handle alternative naming conventions
    elif path_lower.startswith(("sample/", "samples/")):
        return "examples"

    # Skip non-relevant directories
    elif path_lower.startswith(
        (
            "test/",
            "tests/",
            ".github/",
            "docs/",
            "doc/",
            ".terraform/",
            "terraform/",
            ".git/",
            "node_modules/",
            "__pycache__/",
            ".pytest_cache/",
            "coverage/",
        )
    ):
        return None

    # Skip common file extensions that shouldn't be directories
    elif "." in path and not path.endswith("/"):
        return None

    return None


async def _extract_path_descriptions(
    github_client: GitHubClient,
    owner: str,
    repo_name: str,
    version: str,
    categorized_paths: dict[str, list[str]],
) -> dict[str, str]:
    """
    Extract README descriptions for each significant path.

    This function attempts to read README files for each path to extract
    meaningful descriptions. Falls back to generic descriptions if README
    is not available or cannot be read.

    Args:
        github_client: GitHubClient instance
        owner: Repository owner
        repo_name: Repository name
        version: Git reference
        categorized_paths: Categorized paths from tree

    Returns:
        Dictionary mapping paths to their descriptions
    """
    descriptions = {}

    # Extract descriptions for all paths
    for category, paths in categorized_paths.items():
        for path in paths:
            description = await _get_path_description(github_client, owner, repo_name, version, path, category)
            descriptions[path] = description

    return descriptions


async def _get_path_description(
    github_client: GitHubClient,
    owner: str,
    repo_name: str,
    version: str,
    path: str,
    category: str,
) -> str:
    """
    Get description for a specific path by reading its README.

    Args:
        github_client: GitHubClient instance
        owner: Repository owner
        repo_name: Repository name
        version: Git reference
        path: Directory path
        category: Path category

    Returns:
        Description string
    """
    try:
        if path == "":
            # Root module README
            readme_path = "README.md"
        else:
            # Path-specific README
            readme_path = f"{path}/README.md"

        file_content = await github_client.get_file_content(owner, repo_name, readme_path, version)

        if "decoded_content" in file_content:
            readme_text = file_content["decoded_content"]
            summary = _extract_readme_summary(readme_text)
            if summary != "No description available.":
                return summary

    except Exception:
        # README not found or can't be read, will fall back to generic
        pass

    # Use generic description as fallback
    return _get_generic_description(path, category)


def _extract_readme_summary(readme_content: str) -> str:
    """
    Extract a summary from README content.

    This function parses README content to extract the first meaningful
    description paragraph, cleaning up markdown formatting and limiting length.

    Args:
        readme_content: Raw README content

    Returns:
        Summary string, max 200 characters
    """
    if not readme_content.strip():
        return "No description available."

    lines = readme_content.strip().split("\n")
    description_lines = []
    in_code_block = False

    for line in lines:
        line = line.strip()

        # Track code blocks
        if line.startswith("```"):
            in_code_block = not in_code_block
            continue

        # Skip content inside code blocks
        if in_code_block:
            continue

        # Skip empty lines, titles, and markdown headers
        if not line or line.startswith("#") or line.startswith("=") or line.startswith("-"):
            continue

        # Stop at section headers
        if line.startswith("##"):
            break

        # Collect description lines
        description_lines.append(line)

        # Stop after first substantial paragraph
        if len(" ".join(description_lines)) > 100:
            break

    if description_lines:
        # Join lines and clean up markdown formatting
        summary = " ".join(description_lines).strip()
        summary = _clean_markdown(summary)

        # Limit length and ensure proper punctuation
        if len(summary) > 200:
            summary = summary[:197] + "..."
        elif summary and not summary.endswith((".", "!", "?")):
            summary += "."

        return summary

    return "No description available."


def _clean_markdown(text: str) -> str:
    """
    Clean markdown formatting from text.

    Args:
        text: Text with markdown formatting

    Returns:
        Clean text without markdown
    """
    # Remove markdown formatting
    text = re.sub(r"!\[.*?\]\([^)]*\)", "", text)  # Images (must be first)
    text = re.sub(r"\[(.*?)\]\([^)]*\)", r"\1", text)  # Links
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)  # Bold
    text = re.sub(r"\*(.*?)\*", r"\1", text)  # Italic
    text = re.sub(r"`(.*?)`", r"\1", text)  # Inline code
    text = re.sub(r">\s*", "", text)  # Blockquotes
    text = re.sub(r"\s+", " ", text)  # Multiple spaces

    return text.strip()


def _get_generic_description(path: str, category: str) -> str:
    """
    Get a generic description for a path based on its category.

    Args:
        path: Directory path
        category: Path category

    Returns:
        Generic description string
    """
    if category == "root":
        return "Root module containing the main Terraform configuration."
    elif category == "examples":
        return f"Example configuration demonstrating usage of the {path.split('/')[-1]} pattern."
    elif category == "submodules":
        return f"Submodule providing {path.split('/')[-1]} functionality."
    elif category == "solutions":
        return f"Complete solution pattern for {path.split('/')[-1]} deployment."
    else:
        return "Additional module content."


def _format_content_listing(
    module_id: str,
    version: str,
    categorized_paths: dict[str, list[str]],
    path_descriptions: dict[str, str],
) -> str:
    """
    Format the content listing output.

    Args:
        module_id: Module identifier
        version: Version/ref used
        categorized_paths: Categorized paths
        path_descriptions: Path descriptions

    Returns:
        Formatted content listing string
    """
    output = [f"# {module_id} - Available Content"]
    output.append("")
    output.append(f"**Version:** {version}")
    output.append("")

    # Section mapping
    section_titles = {
        "root": "Root Module",
        "examples": "Examples",
        "submodules": "Submodules",
        "solutions": "Solutions",
    }

    for category in ["root", "examples", "submodules", "solutions"]:
        paths = categorized_paths.get(category, [])
        if not paths:
            continue

        output.append(f"## {section_titles[category]}")

        for path in sorted(paths):
            if path == "":
                path_display = "`` (empty string)"
            else:
                path_display = f"`{path}`"

            description = path_descriptions.get(path, "No description available.")

            output.append(f"**Path:** {path_display}")
            output.append(f"**Description:** {description}")
            output.append("")

    return "\n".join(output)
