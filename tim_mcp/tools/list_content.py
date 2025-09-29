"""
List content tool implementation for TIM-MCP.

This tool discovers available paths (examples, submodules) in a
module repository with README summaries to help users navigate the repository
structure and choose appropriate content for their needs.
"""

import re

from ..clients.github_client import GitHubClient
from ..clients.terraform_client import TerraformClient
from ..config import Config
from ..exceptions import (
    ModuleNotFoundError,
    TerraformRegistryError,
)
from ..logging import get_logger
from ..types import ListContentRequest
from ..utils.cache import Cache
from ..utils.module_id import (
    parse_module_id_with_version,
    transform_version_for_github,
)

logger = get_logger(__name__)


async def list_content_impl(request: ListContentRequest, config: Config) -> str:
    """
    Implementation function for the list_content tool.

    Uses Terraform Registry API first for examples and submodules,
    then falls back to GitHub for solutions/patterns directories.

    Args:
        request: ListContentRequest with module_id (may include version)
        config: Configuration instance

    Returns:
        Formatted string with available content paths and descriptions

    Raises:
        ModuleNotFoundError: If module repository is not found
        GitHubError: If GitHub API request fails
        RateLimitError: If GitHub rate limit is exceeded
    """
    # Parse module ID to extract version if included
    namespace, name, provider, version = parse_module_id_with_version(request.module_id)
    base_module_id = f"{namespace}/{name}/{provider}"

    # Initialize clients
    cache = Cache(ttl=config.cache_ttl)
    terraform_client = TerraformClient(config, cache)
    github_client = GitHubClient(config, cache)

    try:
        # Try Registry API first for examples and submodules
        try:
            logger.info(
                "Fetching module structure from Registry API",
                module_id=base_module_id,
                version=version,
            )

            # Get module structure from Registry
            module_data = await terraform_client.get_module_structure(
                namespace, name, provider, version
            )

            # Extract version from Registry response
            resolved_version = module_data.get("version", version)

            # Build categorized paths from Registry data
            categorized_paths = _extract_registry_paths(module_data)

            # Extract descriptions from Registry READMEs
            path_descriptions = _extract_registry_descriptions(module_data)

            logger.info(
                "Successfully fetched from Registry API",
                module_id=base_module_id,
                examples=len(categorized_paths.get("examples", [])),
                submodules=len(categorized_paths.get("submodules", [])),
            )

        except TerraformRegistryError as e:
            # Fall back to full GitHub implementation if Registry fails
            logger.warning(
                "Registry API failed, falling back to GitHub",
                module_id=base_module_id,
                error=str(e),
            )
            return await _list_content_github_fallback(
                base_module_id,
                namespace,
                name,
                provider,
                version,
                config,
                github_client,
            )

        # Return formatted content listing
        return _format_content_listing(
            base_module_id, resolved_version, categorized_paths, path_descriptions
        )

    finally:
        await terraform_client.client.aclose()
        await github_client.client.aclose()


def _extract_registry_paths(module_data: dict) -> dict[str, list[str]]:
    """
    Extract categorized paths from Registry API response.

    Args:
        module_data: Module data from Registry API

    Returns:
        Dictionary mapping category names to lists of paths
    """
    categorized = {"root": [""], "examples": [], "submodules": []}

    # Extract examples
    examples = module_data.get("examples", [])
    for example in examples:
        path = example.get("path", "")
        if path:
            categorized["examples"].append(path)

    # Extract submodules
    submodules = module_data.get("submodules", [])
    for submodule in submodules:
        path = submodule.get("path", "")
        if path:
            categorized["submodules"].append(path)

    return categorized


def _extract_registry_descriptions(module_data: dict) -> dict[str, str]:
    """
    Extract descriptions from Registry API README fields.

    Args:
        module_data: Module data from Registry API

    Returns:
        Dictionary mapping paths to their descriptions
    """
    descriptions = {}

    # Root module description from root README
    root_readme = module_data.get("root", {}).get("readme", "")
    if root_readme:
        descriptions[""] = _extract_readme_summary(root_readme, "root")
    else:
        descriptions[""] = _get_generic_description("", "root")

    # Example descriptions from example READMEs
    examples = module_data.get("examples", [])
    for example in examples:
        path = example.get("path", "")
        readme = example.get("readme", "")
        if path:
            if readme:
                descriptions[path] = _extract_readme_summary(readme, "examples")
            else:
                descriptions[path] = _get_generic_description(path, "examples")

    # Submodule descriptions from submodule READMEs
    submodules = module_data.get("submodules", [])
    for submodule in submodules:
        path = submodule.get("path", "")
        readme = submodule.get("readme", "")
        if path:
            if readme:
                descriptions[path] = _extract_readme_summary(readme, "submodules")
            else:
                descriptions[path] = _get_generic_description(path, "submodules")

    return descriptions


async def _list_content_github_fallback(
    base_module_id: str,
    namespace: str,
    name: str,
    provider: str,
    version: str,
    config: Config,
    github_client: GitHubClient,
) -> str:
    """
    Full GitHub-based implementation as fallback when Registry API fails.

    Args:
        base_module_id: Base module identifier
        namespace: Module namespace
        name: Module name
        provider: Module provider
        version: Module version
        config: Configuration instance
        github_client: GitHubClient instance

    Returns:
        Formatted content listing string
    """
    # Extract repository information from base module ID
    owner, repo_name = _extract_repo_from_module_id(base_module_id)

    # Get repository information
    await github_client.get_repository_info(owner, repo_name)

    # Transform version for GitHub tag lookup (add "v" prefix if needed)
    github_version = transform_version_for_github(version)

    # Resolve version to actual git reference
    resolved_version = await github_client.resolve_version(
        owner, repo_name, github_version
    )

    logger.info(
        "Using GitHub fallback for module",
        module_id=base_module_id,
        owner=owner,
        repo=repo_name,
        version=version,
        resolved_version=resolved_version,
    )

    # Get repository tree structure
    tree_items = await github_client.get_repository_tree(
        owner, repo_name, resolved_version, recursive=True
    )

    # Categorize paths and collect README information
    categorized_paths = _categorize_tree_items(tree_items)

    # Extract README summaries for each significant path
    path_descriptions = await _extract_path_descriptions(
        github_client, owner, repo_name, resolved_version, categorized_paths
    )

    # Return formatted content listing
    return _format_content_listing(
        base_module_id, resolved_version, categorized_paths, path_descriptions
    )


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
        raise ModuleNotFoundError(
            module_id, details={"reason": "Invalid module ID format"}
        )

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
    categorized = {"root": [], "examples": [], "submodules": []}

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
            "patterns/",
            "solutions/",
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
    Extract descriptions for each significant path.

    Uses README files for path descriptions. Falls back to generic
    descriptions if README is not available.

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
            # Use README-based description
            description = await _get_path_description(
                github_client, owner, repo_name, version, path, category
            )
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

        file_content = await github_client.get_file_content(
            owner, repo_name, readme_path, version
        )

        if "decoded_content" in file_content:
            readme_text = file_content["decoded_content"]
            summary = _extract_readme_summary(readme_text, category)
            if summary != "No description available.":
                return summary

    except Exception:
        # README not found or can't be read, will fall back to generic
        pass

    # Use generic description as fallback
    return _get_generic_description(path, category)


def _extract_readme_summary(readme_content: str, path_type: str = "unknown") -> str:
    """
    Extract a summary from README content with type-aware processing.

    This function parses README content to extract meaningful description,
    with different strategies based on the content type (examples vs modules).

    Args:
        readme_content: Raw README content
        path_type: Type of content ("examples", "submodules", "root", "solutions")

    Returns:
        Summary string with length limits based on content type
    """
    if not readme_content.strip():
        return "No description available."

    # No truncation - we want full descriptions but with intelligent content filtering

    lines = readme_content.strip().split("\n")
    description_lines = []
    in_code_block = False
    in_mermaid = False

    # Sections to stop at as they're usually technical docs, not descriptions
    skip_sections = [
        "## Requirements",
        "## Providers",
        "## Modules",
        "## Resources",
        "## Inputs",
        "## Outputs",
        "## Contributing",
        "## License",
        "## Installation",
        "## Getting Started",
        "## Prerequisites",
        "## Running",
        "## Testing",
        "## Development",
        "## Changelog",
    ]

    for line in lines:
        line_stripped = line.strip()

        # Stop at terraform-docs hook for modules
        if "<!-- BEGINNING OF PRE-COMMIT-TERRAFORM DOCS HOOK -->" in line:
            break

        # Stop at common documentation sections that aren't descriptive
        if any(section in line_stripped for section in skip_sections):
            break

        # Track code blocks
        if line_stripped.startswith("```"):
            # Check if it's a Mermaid diagram
            if "mermaid" in line_stripped.lower():
                in_mermaid = True
            in_code_block = not in_code_block
            continue

        # Skip content inside code blocks and Mermaid diagrams
        if in_code_block:
            if in_mermaid and line_stripped.startswith("```"):
                in_mermaid = False
            continue

        # Skip all images, badges, and status indicators
        if "![" in line_stripped and "]" in line_stripped and "(" in line_stripped:
            continue

        # Skip HTML comments and metadata
        if line_stripped.startswith("<!--") or line_stripped.endswith("-->"):
            continue

        # Skip empty lines and main title headers
        if not line_stripped or line_stripped.startswith("# "):
            continue

        # For root modules, intelligently handle section headers
        if line_stripped.startswith("## "):
            # Keep overview/description sections, skip technical ones
            if any(
                keep in line_stripped.lower()
                for keep in [
                    "overview",
                    "description",
                    "about",
                    "what",
                    "features",
                    "summary",
                ]
            ):
                description_lines.append(line_stripped)
            else:
                # Stop at technical sections if we have content
                if description_lines:
                    break
                continue

        # Handle bullet points - preserve them for all types as they contain key info
        if line_stripped.startswith(("-", "*", "+")):
            description_lines.append(line_stripped)
        elif line_stripped.startswith("="):
            # Skip markdown underlines
            continue
        else:
            description_lines.append(line_stripped)

        # Continue collecting all relevant content - no artificial limits

    if description_lines:
        # Join lines and clean up markdown formatting
        summary = " ".join(description_lines).strip()
        summary = _clean_readme_content(summary, path_type)

        # Check for boilerplate text that provides no value
        if _is_boilerplate_description(summary):
            return "No description available."

        # Ensure proper punctuation without truncation
        if summary and not summary.endswith((".", "!", "?")):
            summary += "."

        return summary

    return "No description available."


def _is_boilerplate_description(text: str) -> bool:
    """
    Detect if text is useless boilerplate that should not be returned.

    Args:
        text: Description text to check

    Returns:
        True if text is boilerplate that provides no value
    """
    if not text or len(text.strip()) < 10:
        return True

    boilerplate_patterns = [
        ":exclamation: Important: This solution is not intended to be called by other modules",
        "This solution is not intended to be called by other modules",
        "contains a provider configuration and is not compatible with the for_each",
        "provider configuration and is not compatible with",
        "For more information, see Providers Within Modules",
    ]

    text_lower = text.lower()
    for pattern in boilerplate_patterns:
        if pattern.lower() in text_lower:
            return True

    return False


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


def _clean_readme_content(text: str, path_type: str) -> str:
    """
    Clean README content with enhanced intelligent stripping.

    Args:
        text: Text to clean
        path_type: Type of content (examples, submodules, root, etc.)

    Returns:
        Cleaned text appropriate for the content type
    """
    # Apply basic markdown cleaning
    text = _clean_markdown(text)

    # For examples, preserve list structure but clean it up
    if path_type == "examples":
        # Clean up bullet point formatting
        text = re.sub(r"\s*-\s+", " • ", text)  # Convert - to bullet points
        text = re.sub(r"\s*\*\s+", " • ", text)  # Convert * to bullet points
        text = re.sub(r"\s*\+\s+", " • ", text)  # Convert + to bullet points

    # Remove all images, including any that slipped through
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)  # Full image syntax
    text = re.sub(r"!\[.*?\]", "", text)  # Partial image syntax

    # Remove badges and status indicators more aggressively
    text = re.sub(r"\[!\[.*?\]\]", "", text)  # Nested badge syntax
    text = re.sub(r"Status-\w+", "", text)  # Status badge text
    text = re.sub(
        r"stable|enabled|brightgreen|badge|shield|svg", "", text, flags=re.IGNORECASE
    )

    # Remove Mermaid diagram remnants
    text = re.sub(r"```mermaid[\s\S]*?```", "", text, flags=re.MULTILINE)
    text = re.sub(r"graph|flowchart|sequenceDiagram|classDiagram", "", text)

    # Clean up terraform-docs remnants and table headers
    text = re.sub(r"BEGINNING OF PRE-COMMIT-TERRAFORM DOCS HOOK", "", text)
    text = re.sub(r"\|\s*Name\s*\|\s*Version\s*\|.*?\|", "", text)
    text = re.sub(r"\|[-\s:|]*\|", "", text)  # Table separators

    # Remove HTML and markdown artifacts
    text = re.sub(r"<!--.*?-->", "", text)  # HTML comments
    text = re.sub(r"<[^>]+>", "", text)  # HTML tags
    text = re.sub(r"#{1,6}\s*", "", text)  # Header markers that slipped through

    # Clean up URLs and references
    text = re.sub(r"https?://[^\s)]+", "", text)  # Remove standalone URLs
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # Convert links to text

    # Clean up multiple spaces and normalize whitespace
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*•\s*", " • ", text)  # Normalize bullet spacing
    text = text.strip()

    return text


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
    }

    for category in ["root", "examples", "submodules"]:
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
