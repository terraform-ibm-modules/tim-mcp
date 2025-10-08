"""
Get provider resource details tool implementation for TIM-MCP.

This tool retrieves detailed documentation for a specific provider resource or data source.
"""

from ..clients.terraform_client import TerraformClient
from ..config import Config
from ..exceptions import TerraformRegistryError
from ..parsers.provider_docs import parse_provider_markdown
from ..types import (
    GetProviderResourceDetailsRequest,
    ProviderResourceDetails,
)


def build_documentation_url(namespace: str, name: str, category: str, slug: str) -> str:
    """
    Build the documentation URL for a resource.

    Args:
        namespace: Provider namespace
        name: Provider name
        category: Category (resources or data-sources)
        slug: Resource slug

    Returns:
        Documentation URL
    """
    doc_type = "resources" if category == "resources" else "data-sources"
    return f"https://registry.terraform.io/providers/{namespace}/{name}/latest/docs/{doc_type}/{slug}"


async def get_provider_resource_details_impl(
    request: GetProviderResourceDetailsRequest, config: Config
) -> ProviderResourceDetails:
    """
    Implementation function for the get_provider_resource_details MCP tool.

    Args:
        request: Details request with doc ID and format
        config: Configuration instance

    Returns:
        Provider resource details in requested format

    Raises:
        TerraformRegistryError: If API requests fail
    """
    # Validate format
    if request.format not in ["full", "examples", "schema"]:
        raise TerraformRegistryError(
            f"Invalid format '{request.format}'. Must be 'full', 'examples', or 'schema'"
        )

    # Initialize client and fetch data
    async with TerraformClient(config) as terraform_client:
        try:
            # Get the full document content
            doc_data = await terraform_client.get_provider_doc_content(
                doc_id=request.provider_doc_id
            )

            # Extract metadata
            doc_id = doc_data["data"]["id"]
            attributes = doc_data["data"]["attributes"]

            slug = attributes.get("slug") or ""
            title = attributes.get("title") or ""
            category = attributes.get("category") or ""
            subcategory = attributes.get("subcategory") or ""
            markdown_content = attributes.get("content") or ""

            # Parse the markdown
            parsed = parse_provider_markdown(markdown_content, slug)

            # Extract provider info from doc metadata (if available)
            # For now, we'll use placeholder values since they're not in the v2 API response
            # In a real implementation, we'd need to track this from the search or look it up
            provider_namespace = "IBM-Cloud"  # Default for TIM
            provider_name = "ibm"  # Default for TIM
            provider_version = "latest"  # Would need to be tracked from search

            # Build documentation URL
            doc_url = build_documentation_url(
                provider_namespace, provider_name, category, slug
            )

            # Build the response based on format
            full_markdown = markdown_content if request.format == "full" else None

            details = ProviderResourceDetails(
                provider_doc_id=doc_id,
                slug=slug,
                title=title,
                category=category,
                subcategory=subcategory,
                provider_namespace=provider_namespace,
                provider_name=provider_name,
                provider_version=provider_version,
                description=parsed["description"],
                arguments=parsed["arguments"],
                attributes=parsed["attributes"],
                examples=parsed["examples"],
                full_markdown=full_markdown,
                related_resources=parsed["related_resources"],
                documentation_url=doc_url,
            )

            return details

        except TerraformRegistryError as e:
            # Transform 404 errors to more descriptive messages
            if e.status_code == 404:
                raise TerraformRegistryError(
                    f"Provider documentation with ID '{request.provider_doc_id}' not found",
                    status_code=404,
                ) from e
            # Re-raise other registry errors unchanged
            raise
