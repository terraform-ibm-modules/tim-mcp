"""
Search provider resources and data sources tool implementation for TIM-MCP.

This tool searches provider documentation with multi-field matching and relevance scoring.
"""

import asyncio
import re

from ..clients.terraform_client import TerraformClient
from ..config import Config
from ..exceptions import TerraformRegistryError, ValidationError
from ..tools.get_provider_details import parse_provider_id_with_version
from ..types import (
    ProviderResourceSearchResult,
    SearchProviderResourcesRequest,
    SearchProviderResourcesResponse,
)


def calculate_relevance_score(query_lower: str, doc: dict) -> tuple[int, list[str]]:
    """
    Calculate relevance score for a document based on query match.

    Args:
        query_lower: Lowercase search query
        doc: Document data from API

    Returns:
        Tuple of (score, match_reasons)
    """
    score = 0
    match_reasons = []

    slug = (doc["attributes"].get("slug") or "").lower()
    title = (doc["attributes"].get("title") or "").lower()
    subcategory = (doc["attributes"].get("subcategory") or "").lower()

    # Exact slug match (highest priority)
    if query_lower == slug:
        score += 100
        match_reasons.append("exact_slug_match")
    # Partial slug match
    elif query_lower in slug:
        score += 50
        match_reasons.append("partial_slug_match")
    # Slug with provider prefix
    elif query_lower in slug.replace("_", " "):
        score += 40
        match_reasons.append("fuzzy_slug_match")

    # Title match
    if query_lower in title:
        score += 25
        match_reasons.append("title_match")

    # Subcategory match
    if query_lower in subcategory:
        score += 10
        match_reasons.append("subcategory_match")

    # Handle plurals (vpc matches vpcs)
    if query_lower.endswith("s") and query_lower[:-1] in slug:
        score += 15
        match_reasons.append("plural_match")
    elif not query_lower.endswith("s") and (query_lower + "s") in slug:
        score += 15
        match_reasons.append("singular_match")

    return score, match_reasons


def extract_description_snippet(doc: dict) -> str:
    """
    Extract a brief description from document metadata.

    Args:
        doc: Document data from API

    Returns:
        Description snippet (max 200 chars)
    """
    # Description might be in the path or need to be extracted
    # For now, use the title as a fallback (will be replaced by fetched description)
    title = doc["attributes"].get("title") or "Unknown"
    subcategory = doc["attributes"].get("subcategory") or ""

    if subcategory:
        return f"{title} - {subcategory}"

    return title


async def fetch_description_snippet(
    terraform_client: TerraformClient,
    doc_id: str,
) -> str:
    """
    Fetch and extract description from provider documentation.

    Extracts from markdown frontmatter or first meaningful sentence.

    Args:
        terraform_client: TerraformClient instance
        doc_id: Provider document ID

    Returns:
        Description text (max 200 chars) or empty string on failure
    """
    try:
        doc_data = await terraform_client.get_provider_doc_content(doc_id)
        markdown = doc_data["data"]["attributes"].get("content") or ""

        # Try to extract from frontmatter: description: |-
        match = re.search(
            r"description:\s*\|-?\s*\n\s*([^\n]+)", markdown, re.MULTILINE
        )
        if match:
            desc = match.group(1).strip()
            return desc[:200] + "..." if len(desc) > 200 else desc

        # Fallback: find first non-header, non-frontmatter text
        lines = markdown.split("\n")
        in_frontmatter = False
        for line in lines:
            if line.strip() == "---":
                in_frontmatter = not in_frontmatter
                continue

            if not in_frontmatter and line.strip():
                # Skip headers
                if not line.startswith("#"):
                    sentence = line.strip()
                    # Get first sentence
                    if "." in sentence:
                        sentence = sentence[: sentence.index(".") + 1]
                    return sentence[:200]

        return ""
    except Exception:
        # Fail gracefully - don't break search if one doc fails
        return ""


async def search_provider_resources_impl(
    request: SearchProviderResourcesRequest, config: Config
) -> SearchProviderResourcesResponse:
    """
    Implementation function for the search_provider_resources MCP tool.

    Args:
        request: Search request with query and filters
        config: Configuration instance

    Returns:
        Search response with ranked results

    Raises:
        ValidationError: If parameters are invalid
        TerraformRegistryError: If API requests fail
    """
    # Parse provider ID
    try:
        namespace, name, version = parse_provider_id_with_version(request.provider_id)
    except ValidationError as e:
        raise TerraformRegistryError(f"Provider ID validation failed: {e}") from e

    # Initialize client and fetch data
    async with TerraformClient(config) as terraform_client:
        try:
            # Get provider version ID
            version_id = await terraform_client.get_provider_version_id(
                namespace=namespace,
                name=name,
                version=version,
            )

            # Fetch docs for specified categories
            all_docs = []

            if request.category is None:
                # Fetch both resources and data-sources
                resources = await terraform_client.list_provider_docs(
                    provider_version_id=version_id,
                    category="resources",
                )
                data_sources = await terraform_client.list_provider_docs(
                    provider_version_id=version_id,
                    category="data-sources",
                )
                all_docs = resources + data_sources
            else:
                # Fetch only the specified category
                all_docs = await terraform_client.list_provider_docs(
                    provider_version_id=version_id,
                    category=request.category,
                )

            # Filter and rank results
            query_lower = request.query.lower()
            scored_results = []

            for doc in all_docs:
                # Apply subcategory filter if specified
                if request.subcategory:
                    doc_subcategory = doc["attributes"].get("subcategory") or ""
                    if request.subcategory.lower() not in doc_subcategory.lower():
                        continue

                # Calculate relevance score
                score, match_reasons = calculate_relevance_score(query_lower, doc)

                # Only include if there's a match
                if score > 0:
                    result = ProviderResourceSearchResult(
                        provider_doc_id=doc.get("id", ""),
                        slug=doc["attributes"].get("slug") or "",
                        title=doc["attributes"].get("title") or "",
                        category=doc["attributes"].get("category") or "",
                        subcategory=doc["attributes"].get("subcategory") or "",
                        description=extract_description_snippet(doc),
                        relevance_score=score,
                        match_reasons=match_reasons,
                    )
                    scored_results.append(result)

            # Sort by relevance score (descending)
            scored_results.sort(key=lambda x: x.relevance_score, reverse=True)

            # Fetch real descriptions for top results (concurrent for speed)
            if scored_results:
                # Limit concurrent fetches to avoid overwhelming API
                fetch_limit = min(len(scored_results), request.limit)

                # Fetch descriptions concurrently using asyncio.gather
                tasks = [
                    fetch_description_snippet(terraform_client, result.provider_doc_id)
                    for result in scored_results[:fetch_limit]
                ]

                # Gather with return_exceptions to handle failures gracefully
                descriptions = await asyncio.gather(*tasks, return_exceptions=True)

                # Update results with fetched descriptions
                for i, desc in enumerate(descriptions):
                    if isinstance(desc, str) and desc:
                        scored_results[i].description = desc
                    # Keep existing placeholder description if fetch failed

            # Apply limit
            limited_results = scored_results[: request.limit]

            # Get actual provider version from version_id lookup
            # For now, use "latest" or the requested version
            provider_version = version if version != "latest" else "latest"

            return SearchProviderResourcesResponse(
                provider_id=request.provider_id,
                provider_version=provider_version,
                query=request.query,
                category=request.category,
                subcategory=request.subcategory,
                total_found=len(scored_results),
                returned=len(limited_results),
                results=limited_results,
            )

        except TerraformRegistryError as e:
            # Transform 404 errors to more descriptive messages
            if e.status_code == 404:
                raise TerraformRegistryError(
                    f"Provider '{namespace}/{name}' not found or no documentation available",
                    status_code=404,
                ) from e
            # Re-raise other registry errors unchanged
            raise
