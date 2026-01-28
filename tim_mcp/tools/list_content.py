"""
List content tool implementation for TIM-MCP.

This tool discovers available paths (examples, submodules, solutions) in a
module repository with README summaries to help users navigate the repository
structure and choose appropriate content for their needs.
"""

import json
import re

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..clients.github_client import GitHubClient
from ..config import Config
from ..context import get_cache, get_rate_limiter
from ..exceptions import GitHubError, ModuleNotFoundError, RateLimitError
from ..logging import get_logger
from ..types import ListContentRequest
from ..utils.module_id import (
    parse_module_id_with_version,
    transform_version_for_github,
)

logger = get_logger(__name__)


async def list_content_impl(request: ListContentRequest, config: Config) -> str:
    """
    Implementation function for the list_content tool.

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

    # Extract repository information from base module ID
    owner, repo_name = _extract_repo_from_module_id(base_module_id)

    # Initialize GitHub client with shared cache and rate limiter
    cache = get_cache()
    rate_limiter = get_rate_limiter()
    github_client = GitHubClient(config, cache=cache, rate_limiter=rate_limiter)

    try:
        # Get repository information
        await github_client.get_repository_info(owner, repo_name)

        # Transform version for GitHub tag lookup (add "v" prefix if needed)
        github_version = transform_version_for_github(version)

        # Resolve version to actual git reference
        resolved_version = await github_client.resolve_version(
            owner, repo_name, github_version
        )

        logger.info(
            "Listing content for module",
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

        # Format output
        # Return formatted content listing
        return _format_content_listing(
            base_module_id, resolved_version, categorized_paths, path_descriptions
        )
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
    Extract descriptions for each significant path.

    For solutions, uses ibm_catalog.json descriptions. For other paths,
    uses README files. Falls back to generic descriptions if neither
    is available.

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

    # Check if we have solutions - if so, try to load catalog descriptions
    catalog_descriptions = {}
    if "solutions" in categorized_paths and categorized_paths["solutions"]:
        catalog_descriptions = await _get_catalog_descriptions(
            github_client, owner, repo_name, version
        )

    # Extract descriptions for all paths
    for category, paths in categorized_paths.items():
        for path in paths:
            # For solutions, try catalog description first
            if category == "solutions" and path in catalog_descriptions:
                descriptions[path] = catalog_descriptions[path]
            else:
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


@retry(
    stop=stop_after_attempt(5),  # More attempts for rate limits
    wait=wait_exponential(multiplier=2, min=4, max=60),  # Longer waits for rate limits
    retry=retry_if_exception_type((RateLimitError, GitHubError)),
)
async def _fetch_catalog_with_retry(
    github_client: GitHubClient,
    owner: str,
    repo_name: str,
    version: str,
) -> dict[str, any] | None:
    """
    Fetch ibm_catalog.json with intelligent retry logic for rate limits.

    Args:
        github_client: GitHubClient instance
        owner: Repository owner
        repo_name: Repository name
        version: Git reference

    Returns:
        Parsed catalog data or None if failed

    Raises:
        RateLimitError: If rate limited after all retries
        GitHubError: If other GitHub errors persist after retries
    """
    try:
        file_content = await github_client.get_file_content(
            owner, repo_name, "ibm_catalog.json", version
        )

        if "decoded_content" not in file_content:
            return None

        return json.loads(file_content["decoded_content"])

    except RateLimitError as e:
        logger.warning(
            "Rate limited fetching catalog, will retry",
            repo=f"{owner}/{repo_name}",
            reset_time=e.reset_time,
        )
        raise  # Let tenacity handle the retry

    except GitHubError as e:
        if e.status_code == 404:
            # File doesn't exist, no point retrying
            logger.debug(
                "Catalog file not found",
                repo=f"{owner}/{repo_name}",
                path="ibm_catalog.json",
            )
            return None
        else:
            # Other GitHub errors might be transient
            logger.warning(
                "GitHub error fetching catalog, will retry",
                repo=f"{owner}/{repo_name}",
                error=str(e),
                status_code=e.status_code,
            )
            raise

    except Exception as e:
        # JSON parsing or other errors - no point retrying
        logger.debug(
            "Failed to parse catalog", repo=f"{owner}/{repo_name}", error=str(e)
        )
        return None


async def _get_catalog_descriptions(
    github_client: GitHubClient,
    owner: str,
    repo_name: str,
    version: str,
) -> dict[str, str]:
    """
    Fetch and parse ibm_catalog.json to extract solution descriptions.

    Args:
        github_client: GitHubClient instance
        owner: Repository owner
        repo_name: Repository name
        version: Git reference

    Returns:
        Dictionary mapping working_directory paths to descriptions
    """
    try:
        # Try to fetch ibm_catalog.json with retry logic
        catalog = await _fetch_catalog_with_retry(
            github_client, owner, repo_name, version
        )

        if not catalog:
            return {}

        descriptions = {}

        # Parse products/flavors (solutions) - check both formats
        catalog_items = []
        if "flavors" in catalog:
            catalog_items = catalog["flavors"]
        elif "products" in catalog:
            # Some catalogs use 'products' containing 'flavors'
            for product in catalog["products"]:
                if "flavors" in product:
                    catalog_items.extend(product["flavors"])
                # Also treat the product itself as a catalog item
                catalog_items.append(product)

        for flavor in catalog_items:
            working_dir = flavor.get("working_directory", "")
            if not working_dir:
                continue

            # Build comprehensive description from catalog data
            description_parts = []

            # Add label as primary description
            if "label" in flavor:
                description_parts.append(flavor["label"])

            # Add product short description (important high-level context)
            for desc_field in ["short_description", "long_description", "description"]:
                if desc_field in flavor:
                    desc = flavor[desc_field].strip()
                    if desc and desc not in description_parts:
                        description_parts.append(desc)

            # Add ALL architecture features (comprehensive feature list)
            if "architecture" in flavor:
                arch = flavor["architecture"]

                # Features are in an array - include ALL of them
                if "features" in arch and isinstance(arch["features"], list):
                    for feature in arch["features"]:
                        if isinstance(feature, str) and feature.strip():
                            feature_text = feature.strip()
                            if feature_text not in description_parts:
                                description_parts.append(feature_text)

                # Architecture description if available
                if "description" in arch:
                    arch_desc = arch["description"].strip()
                    if arch_desc and arch_desc not in description_parts:
                        description_parts.append(arch_desc)

                # Diagram descriptions provide deployment context
                if "diagrams" in arch and isinstance(arch["diagrams"], list):
                    for diagram in arch["diagrams"]:
                        if isinstance(diagram, dict) and "description" in diagram:
                            desc = diagram["description"].strip()
                            if desc:
                                # Clean up the description to be more readable
                                desc = desc.replace("This variation", "This solution")
                                desc = desc.replace("This deployment", "This solution")
                                if desc not in description_parts:
                                    description_parts.append(desc)

                # Add any other descriptive fields in architecture
                for field in ["summary", "overview", "purpose"]:
                    if field in arch and isinstance(arch[field], str):
                        field_desc = arch[field].strip()
                        if field_desc and field_desc not in description_parts:
                            description_parts.append(field_desc)

            # Combine all parts
            if description_parts:
                # Clean up each part to avoid double periods
                cleaned_parts = []
                for part in description_parts:
                    part = part.rstrip(".")
                    if part:
                        cleaned_parts.append(part)

                if cleaned_parts:
                    description = ". ".join(cleaned_parts) + "."
                    descriptions[working_dir] = description

        logger.info(
            "Loaded catalog descriptions",
            repo=f"{owner}/{repo_name}",
            solution_count=len(descriptions),
        )
        return descriptions

    except Exception as e:
        logger.debug(
            "Failed to load catalog descriptions",
            repo=f"{owner}/{repo_name}",
            error=str(e),
        )
        return {}


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
        # Provide meaningful descriptions based on common solution patterns
        solution_name = path.split("/")[-1]

        if "quickstart" in solution_name.lower():
            return "Quickstart solution for rapid deployment. Provides a simplified configuration to get started quickly with minimal setup and basic infrastructure components."
        elif (
            "fully-configurable" in solution_name.lower()
            or "complete" in solution_name.lower()
        ):
            return "Fully configurable solution offering comprehensive control over all infrastructure parameters, service integrations, and advanced deployment options."
        elif "standard" in solution_name.lower():
            return "Standard solution providing a balanced configuration with commonly used infrastructure patterns and best practices."
        elif "basic" in solution_name.lower():
            return "Basic solution with essential infrastructure components for straightforward deployments."
        else:
            return f"Pre-configured solution pattern for {solution_name} deployment with optimized settings and infrastructure components."
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
