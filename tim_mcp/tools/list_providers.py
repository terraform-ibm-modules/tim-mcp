"""
Provider listing tool implementation for TIM-MCP.

This module provides the list_providers functionality for listing all allowlisted
Terraform providers with optional filtering.
"""

import asyncio
from datetime import datetime

from ..clients.terraform_client import TerraformClient
from ..config import Config
from ..exceptions import TIMError
from ..types import ProviderInfo
from ..utils.version import get_latest_stable_version, is_stable_version


def _parse_provider_id(provider_id: str) -> tuple[str, str] | None:
    """
    Parse a provider ID into namespace and name.

    Args:
        provider_id: Provider ID in format "namespace/name"

    Returns:
        Tuple of (namespace, name) or None if invalid
    """
    parts = provider_id.strip().split("/")
    if len(parts) != 2:
        return None
    namespace, name = parts
    if not namespace or not name:
        return None
    return namespace, name


def _matches_filter(provider: ProviderInfo, filter_keyword: str) -> bool:
    """
    Check if provider matches the filter keyword.

    Args:
        provider: ProviderInfo object to check
        filter_keyword: Keyword to match (case-insensitive)

    Returns:
        True if provider matches filter, False otherwise
    """
    keyword_lower = filter_keyword.lower()
    return (
        keyword_lower in provider.namespace.lower()
        or keyword_lower in provider.name.lower()
        or keyword_lower in provider.description.lower()
    )


async def _fetch_provider(
    terraform_client: TerraformClient,
    namespace: str,
    name: str,
) -> ProviderInfo | None:
    """
    Fetch a single provider's information.

    Args:
        terraform_client: TerraformClient instance
        namespace: Provider namespace
        name: Provider name

    Returns:
        ProviderInfo object or None if fetch fails
    """
    from ..logging import get_logger

    logger = get_logger(__name__)

    try:
        provider_data = await terraform_client.get_provider_info(namespace, name)

        # Parse published_at datetime
        published_at_str = provider_data.get("published_at", "")
        if published_at_str.endswith("Z"):
            published_at_str = published_at_str[:-1] + "+00:00"
        published_at = datetime.fromisoformat(published_at_str)

        # Extract version
        version = provider_data["version"]

        # Check if version is pre-release
        if not is_stable_version(version):
            logger.info(
                "Provider has pre-release version, fetching stable version",
                provider_id=f"{namespace}/{name}",
                pre_release_version=version,
            )

            # Fetch detailed provider info to get versions list
            try:
                details = await terraform_client.get_provider_details(
                    namespace=namespace, name=name
                )
                versions = details.get("versions", [])
                stable_version = get_latest_stable_version(versions)

                if not stable_version:
                    logger.info(
                        "No stable versions found for provider, excluding",
                        provider_id=f"{namespace}/{name}",
                    )
                    return None

                logger.info(
                    "Found stable version for provider",
                    provider_id=f"{namespace}/{name}",
                    stable_version=stable_version,
                )

                # Fetch complete details for the stable version
                stable_details = await terraform_client.get_provider_details(
                    namespace=namespace, name=name, version=stable_version
                )

                # Update all fields from stable version details
                provider_data = stable_details
                version = stable_version

                # Parse published_at from stable version
                published_at_str = provider_data.get("published_at", "")
                if published_at_str.endswith("Z"):
                    published_at_str = published_at_str[:-1] + "+00:00"
                published_at = datetime.fromisoformat(published_at_str)

            except Exception as e:
                logger.warning(
                    "Failed to fetch stable provider details, excluding",
                    provider_id=f"{namespace}/{name}",
                    error=str(e),
                )
                return None

        # Create ProviderInfo object
        return ProviderInfo(
            id=provider_data["id"],
            namespace=provider_data["namespace"],
            name=provider_data["name"],
            version=version,
            description=provider_data.get("description", ""),
            source_url=provider_data["source"],
            downloads=provider_data.get("downloads", 0),
            tier=provider_data.get("tier", "community"),
            published_at=published_at,
        )
    except Exception as e:
        logger.warning(
            f"Failed to fetch provider {namespace}/{name}: {e}",
            namespace=namespace,
            name=name,
            error=str(e),
        )
        return None


async def list_providers_impl(
    filter_keyword: str | None,
    config: Config,
) -> list[ProviderInfo]:
    """
    Implementation function for the list_providers MCP tool.

    This function fetches all allowlisted providers in parallel and returns
    them with optional filtering.

    Args:
        filter_keyword: Optional keyword to filter providers
        config: Configuration instance for client setup

    Returns:
        List of ProviderInfo objects sorted by downloads (descending)

    Raises:
        TIMError: When all provider fetches fail
    """
    from ..logging import get_logger

    logger = get_logger(__name__)

    # Parse all provider IDs from config
    provider_ids = []
    for provider_id in config.allowed_provider_ids:
        parsed = _parse_provider_id(provider_id)
        if parsed:
            provider_ids.append(parsed)
        else:
            logger.warning(
                f"Invalid provider ID in config: {provider_id}",
                provider_id=provider_id,
            )

    if not provider_ids:
        logger.error("No valid provider IDs found in configuration")
        raise TIMError("No providers configured")

    # Fetch all providers in parallel
    async with TerraformClient(config) as terraform_client:
        fetch_tasks = [
            _fetch_provider(terraform_client, namespace, name)
            for namespace, name in provider_ids
        ]
        results = await asyncio.gather(*fetch_tasks, return_exceptions=False)

    # Filter out None results (failed fetches)
    providers = [p for p in results if p is not None]

    if not providers:
        logger.error("All provider fetches failed")
        raise TIMError("Failed to fetch any providers")

    # Apply filter if provided
    if filter_keyword:
        providers = [p for p in providers if _matches_filter(p, filter_keyword)]
        logger.info(
            f"Filtered providers by keyword: {filter_keyword}",
            filter_keyword=filter_keyword,
            providers_found=len(providers),
        )

    # Sort by downloads (descending)
    providers.sort(key=lambda p: p.downloads, reverse=True)

    logger.info(
        "Provider list completed",
        filter_keyword=filter_keyword,
        providers_found=len(providers),
    )

    return providers
