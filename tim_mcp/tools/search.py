"""
Search tool implementation for TIM-MCP.

This module provides the search_modules functionality for finding Terraform modules
in the Terraform Registry with comprehensive error handling and data transformation.

The implementation follows these principles:
- Comprehensive input validation using Pydantic models
- Graceful error handling with appropriate exception types
- Proper async context manager usage for resource cleanup
- Data transformation to match the tool specification format
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ..clients.github_client import GitHubClient
from ..clients.terraform_client import TerraformClient
from ..config import Config
from ..context import get_cache, get_rate_limiter
from ..exceptions import TIMError
from ..exceptions import ValidationError as TIMValidationError
from ..types import ModuleInfo, ModuleSearchRequest, ModuleSearchResponse

# Required topics that must be present in the GitHub repository
REQUIRED_TOPICS = ["core-team"]


def _validate_api_response_structure(api_response: Any) -> None:
    """
    Validate the structure of the API response from Terraform Registry.

    Args:
        api_response: Raw API response to validate

    Raises:
        ValidationError: When the API response structure is invalid
    """
    if not isinstance(api_response, dict):
        raise TIMValidationError("Invalid API response format: expected dictionary")

    if "modules" not in api_response:
        raise TIMValidationError("Invalid API response format: missing 'modules' field")

    if "meta" not in api_response:
        raise TIMValidationError("Invalid API response format: missing 'meta' field")

    # Validate modules is a list
    if not isinstance(api_response["modules"], list):
        raise TIMValidationError(
            "Invalid API response format: 'modules' must be a list"
        )

    # Validate meta has required fields
    meta = api_response["meta"]
    if not isinstance(meta, dict):
        raise TIMValidationError(
            "Invalid API response format: 'meta' must be a dictionary"
        )


async def search_modules_impl(
    request: ModuleSearchRequest, config: Config
) -> ModuleSearchResponse:
    """
    Implementation function for the search_modules MCP tool.

    This function searches for Terraform modules in the registry using the provided
    search criteria and returns formatted results. It handles API communication,
    validates responses, and transforms data to match the tool specification.

    Args:
        request: The validated search request containing query parameters
        config: Configuration instance for client setup and behavior

    Returns:
        ModuleSearchResponse containing search results with properly formatted module data

    Raises:
        TerraformRegistryError: When the Terraform Registry API fails
        RateLimitError: When API rate limits are exceeded
        ValidationError: When the API response format is invalid or malformed
    """
    from ..logging import get_logger

    logger = get_logger(__name__)

    # Search the local index first — fast, no API call needed.
    # Covers name, keyword, service, category, use case, and submodule tag searches.
    # Falls back to the live Terraform Registry API only when the index has no match,
    # avoiding unnecessary API calls and rate limit exhaustion.
    index_result = _search_index(request.query, request.limit)
    if index_result is not None:
        logger.info("Search served from local index", query=request.query, total=index_result.total_found)
        return index_result

    # Fall back to live Terraform Registry API when index has no match
    # Use the configured namespace (always the first allowed namespace)
    namespace = config.allowed_namespaces[0] if config.allowed_namespaces else None

    # Create and use both Terraform and GitHub clients as async context managers
    # Use shared cache and rate limiter from context
    cache = get_cache()
    rate_limiter = get_rate_limiter()

    async with (
        TerraformClient(
            config, cache=cache, rate_limiter=rate_limiter
        ) as terraform_client,
        GitHubClient(config, cache=cache, rate_limiter=rate_limiter) as github_client,
    ):
        try:
            # We need to fetch and validate modules until we have enough valid ones
            validated_modules = []
            offset = 0
            batch_size = 50  # Fetch modules in smaller batches
            max_attempts = 10  # Prevent infinite loops

            # Track the total count from the first API response
            total_count = 0

            attempt = 0
            while len(validated_modules) < request.limit and attempt < max_attempts:
                attempt += 1

                # Call the Terraform Registry API with search parameters
                api_response = await terraform_client.search_modules(
                    query=request.query,
                    namespace=namespace,
                    limit=batch_size,
                    offset=offset,
                )

                # Validate API response structure before processing
                _validate_api_response_structure(api_response)

                # Extract metadata from response
                meta = api_response["meta"]

                # Capture total_count from the first batch only
                # Subsequent batches might have inconsistent or missing total_count
                if attempt == 1:
                    total_count = meta.get("total_count", 0)

                # If no more modules available, break
                if not api_response["modules"]:
                    logger.info(
                        "No more modules available from Terraform Registry",
                        offset=offset,
                        total_validated=len(validated_modules),
                    )
                    break

                # Transform and validate each module's data
                batch_modules = []
                for i, module_data in enumerate(api_response["modules"]):
                    try:
                        module = _transform_module_data(module_data)

                        # Always fetch the latest stable version since the search API
                        # may return outdated versions with stale metadata (description, etc.)
                        try:
                            versions = await terraform_client.get_module_versions(
                                module.namespace, module.name, module.provider
                            )
                            if versions:
                                # The versions are already filtered to stable only
                                # Use the first one (latest stable)
                                latest_stable = versions[0]

                                # Fetch the module details for the latest version to get accurate metadata
                                latest_module_data = (
                                    await terraform_client.get_module_details(
                                        module.namespace,
                                        module.name,
                                        module.provider,
                                        latest_stable,
                                    )
                                )

                                # Use description from latest version (more accurate)
                                latest_description = latest_module_data.get(
                                    "description", module.description
                                )

                                # Update the module with latest version and metadata
                                module = ModuleInfo(
                                    id=f"{module.namespace}/{module.name}/{module.provider}",
                                    namespace=module.namespace,
                                    name=module.name,
                                    provider=module.provider,
                                    version=latest_stable,
                                    description=latest_description,
                                    source_url=module.source_url,
                                    downloads=module.downloads,
                                    verified=module.verified,
                                    published_at=module.published_at,
                                )

                                if module_data["version"] != latest_stable:
                                    logger.info(
                                        "Updated to latest stable version",
                                        module_id=module.id,
                                        old_version=module_data["version"],
                                        new_version=latest_stable,
                                    )
                            else:
                                # No stable versions available, skip this module
                                logger.warning(
                                    "No stable versions available for module, skipping",
                                    module_id=module.id,
                                )
                                continue
                        except Exception as e:
                            logger.warning(
                                "Failed to fetch latest version for module, using search result version",
                                module_id=module.id,
                                error=str(e),
                            )

                        # Apply module exclusion filtering
                        if _is_module_excluded(module.id, config.excluded_modules):
                            logger.info(
                                "Module excluded from results", module_id=module.id
                            )
                            continue

                        batch_modules.append(module)
                    except Exception as e:
                        # Include context about which module failed
                        logger.warning(
                            f"Invalid module data at offset {offset + i}: {e}",
                            module_data=module_data,
                        )
                        continue

                # Sort this batch by downloads in descending order
                batch_modules.sort(key=lambda m: m.downloads, reverse=True)

                # Validate repositories for modules in this batch
                for module in batch_modules:
                    if len(validated_modules) >= request.limit:
                        break

                    # Check if repository meets our criteria
                    if await _is_repository_valid(module, github_client, logger):
                        validated_modules.append(module)

                # Move to next batch
                offset += batch_size

                logger.info(
                    "Processed batch of modules",
                    batch_size=len(batch_modules),
                    validated_count=len(validated_modules),
                    target_limit=request.limit,
                    offset=offset,
                )

            # Ensure we don't exceed the requested limit
            final_modules = validated_modules[: request.limit]

            # Since the Terraform Registry API doesn't return total_count,
            # we use the actual number of modules we found and validated
            # If total_count was provided in the API response, use that; otherwise use our count
            result_total = total_count if total_count > 0 else len(final_modules)

            logger.info(
                "Search completed",
                total_found=result_total,
                modules_validated=len(final_modules),
                attempts=attempt,
            )

            # Create and return the formatted response
            return ModuleSearchResponse(
                query=request.query,
                total_found=result_total,
                modules=final_modules,
            )

        except TIMError:
            # Re-raise TIM errors as-is to preserve error context
            raise
        except Exception as e:
            # Wrap unexpected errors with context
            raise TIMValidationError(
                f"Unexpected error processing search results: {e}"
            ) from e


def _transform_module_data(module_data: dict[str, Any]) -> ModuleInfo:
    """
    Transform raw module data from the API into a ModuleInfo object.

    This function validates required fields, handles datetime conversion,
    and creates a properly typed ModuleInfo object.

    NOTE: The version field from the API may be a pre-release version.
    The caller should replace it with the latest stable version if needed.

    Args:
        module_data: Raw module data from the Terraform Registry API

    Returns:
        ModuleInfo object with validated and transformed data

    Raises:
        ValueError: When required fields are missing or invalid
        TypeError: When field types are unexpected
    """
    # Validate required fields exist
    required_fields = [
        "id",
        "namespace",
        "name",
        "provider",
        "version",
        "description",
        "source",
    ]
    missing_fields = [field for field in required_fields if field not in module_data]
    if missing_fields:
        raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

    # Transform the published_at datetime
    published_at_str = module_data.get("published_at", "")
    if not published_at_str:
        raise ValueError("Missing or empty 'published_at' field")

    try:
        # Handle the ISO format with 'Z' suffix (common in Terraform Registry)
        if published_at_str.endswith("Z"):
            published_at_str = published_at_str[:-1] + "+00:00"
        published_at = datetime.fromisoformat(published_at_str)
    except (ValueError, TypeError) as e:
        raise ValueError(
            f"Invalid published_at format '{published_at_str}': {e}"
        ) from e

    # Validate and get optional fields with defaults
    downloads = module_data.get("downloads", 0)
    if not isinstance(downloads, int) or downloads < 0:
        downloads = 0  # Fallback to 0 for invalid download counts

    verified = module_data.get("verified", False)
    if not isinstance(verified, bool):
        verified = False  # Fallback to False for invalid verification status

    # Create and return the ModuleInfo object
    # Pydantic will perform additional validation on the fields
    try:
        return ModuleInfo(
            id=module_data["id"],
            namespace=module_data["namespace"],
            name=module_data["name"],
            provider=module_data["provider"],
            version=module_data["version"],
            description=module_data["description"],
            source_url=module_data["source"],  # Pydantic validates as HttpUrl
            downloads=downloads,
            verified=verified,
            published_at=published_at,
        )
    except Exception as e:
        raise ValueError(f"Failed to create ModuleInfo object: {e}") from e


def _is_module_excluded(module_id: str, excluded_modules: list[str]) -> bool:
    """
    Check if a module ID is in the exclusion list.

    Args:
        module_id: The full module identifier (e.g., "terraform-ibm-modules/vpc/ibm")
        excluded_modules: List of module IDs to exclude

    Returns:
        True if the module should be excluded, False otherwise
    """
    return module_id in excluded_modules


async def _is_repository_valid(
    module: ModuleInfo, github_client: GitHubClient, logger
) -> bool:
    """
    Validate if a repository meets our criteria (not archived, has required topics).

    Args:
        module: Module information containing source URL
        github_client: GitHub client to fetch repository info
        logger: Logger instance for logging

    Returns:
        True if the repository meets all criteria, False otherwise
    """
    try:
        # Parse GitHub URL from source URL
        repo_info = github_client.parse_github_url(str(module.source_url))
        if not repo_info:
            logger.warning(
                "Could not parse GitHub URL from source",
                module_id=module.id,
                source_url=str(module.source_url),
            )
            return False

        owner, repo_name = repo_info

        # Get repository information
        repo_data = await github_client.get_repository_info(owner, repo_name)

        # Check if repository is archived
        if repo_data.get("archived", False):
            logger.info(
                "Repository is archived, excluding module",
                module_id=module.id,
                repo=f"{owner}/{repo_name}",
            )
            return False

        # Check if repository has all required topics
        repo_topics = repo_data.get("topics", [])
        missing_topics = [
            topic for topic in REQUIRED_TOPICS if topic not in repo_topics
        ]

        if missing_topics:
            logger.info(
                "Repository missing required topics, excluding module",
                module_id=module.id,
                repo=f"{owner}/{repo_name}",
                missing_topics=missing_topics,
                required_topics=REQUIRED_TOPICS,
                repo_topics=repo_topics,
            )
            return False

        logger.info(
            "Repository passed validation",
            module_id=module.id,
            repo=f"{owner}/{repo_name}",
            repo_topics=repo_topics,
        )
        return True

    except Exception as e:
        logger.warning(
            "Failed to validate repository, excluding module",
            module_id=module.id,
            source_url=str(module.source_url),
            error=str(e),
        )
        return False


def _search_index(query: str, limit: int) -> ModuleSearchResponse | None:
    """
    Search the local module index by matching the query against all relevant
    fields. This fills the gaps left by the live Terraform Registry API which
    only supports free-text search by module name.

    Args:
        query: Search term to match (e.g. "vpc", "security", "key protect")
        limit: Maximum number of results to return

    Returns:
        ModuleSearchResponse if any modules matched, None if no matches found
        (caller then falls back to the live Terraform Registry API).
        Each module id has the version stripped so it is consumable directly
        by other tools such as get_module_details and list_content.
    """
    # Locate module_index.json — check both packaged and dev layouts
    for candidate in [
        Path(__file__).parent.parent / "static" / "module_index.json",
        Path(__file__).parent.parent.parent / "static" / "module_index.json",
    ]:
        if candidate.exists():
            index_path = candidate
            break
    else:
        return None

    with open(index_path) as f:
        data = json.load(f)

    # Remove common stop words that carry no search meaning
    stop_words = {
        "a", "an", "the", "to", "of", "in", "for", "and", "or", "is", "with",
        "create", "use", "using", "setup", "set", "get", "how", "i", "my", "me",
    }
    words = [w for w in query.lower().split() if w not in stop_words]

    # If all words were stop words, fall back to the full query as one phrase
    if not words:
        words = [query.lower()]

    # Require all meaningful words to match — prevents a single common word like
    # "vpc" from matching dozens of unrelated modules in a multi-word query
    threshold = len(words)

    scored: list[tuple[int, dict]] = []

    for m in data["modules"]:
        # Combine all searchable fields into one string so a single query can
        # match by name, keyword, service, category, use case, or submodule tag
        searchable = " ".join([
            m.get("name", ""),
            m.get("description", ""),
            m.get("category", ""),
            m.get("readme_excerpt", "") or "",
            " ".join(s.get("name", "") for s in m.get("submodules", [])),
            " ".join(s.get("description", "") for s in m.get("submodules", [])),
        ]).lower()

        match_count = sum(1 for w in words if w in searchable)
        if match_count < threshold:
            continue

        scored.append((match_count, m))

    # Sort by number of matching words — best matches first
    scored.sort(key=lambda x: x[0], reverse=True)

    matched: list[ModuleInfo] = []
    for _, m in scored:

        # The index id is "namespace/name/provider/version" — strip the version
        # so the returned id works directly with other tools
        raw_id = m["id"]
        parts = raw_id.split("/")
        module_id = "/".join(parts[:3]) if len(parts) == 4 else raw_id
        version = parts[3] if len(parts) == 4 else ""

        try:
            matched.append(ModuleInfo(
                id=module_id,
                namespace=parts[0] if parts else "",
                name=m["name"],
                provider=parts[2] if len(parts) >= 3 else "",
                version=version,
                description=m.get("description", ""),
                source_url=m["source_url"],
                downloads=m.get("downloads", 0),
                verified=False,
                published_at=datetime.fromisoformat(
                    m["published_at"].replace("Z", "+00:00")
                ),
            ))
        except Exception:
            continue

        if len(matched) >= limit:
            break

    if not matched:
        return None

    return ModuleSearchResponse(
        query=query,
        total_found=len(matched),
        modules=matched,
    )
