"""
Shared type definitions for TIM-MCP.

This module contains Pydantic models and type definitions used throughout
the TIM-MCP server for request/response validation and schema generation.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class ModuleSearchRequest(BaseModel):
    """Request model for module search."""

    query: str = Field(..., min_length=1, description="Search term")
    limit: int = Field(5, ge=1, le=100, description="Maximum results to return")


class ModuleInfo(BaseModel):
    """Module information from registry search."""

    id: str = Field(..., description="Full module identifier")
    namespace: str = Field(..., description="Module publisher")
    name: str = Field(..., description="Module name")
    provider: str = Field(..., description="Primary provider")
    version: str = Field(..., description="Latest version")
    description: str = Field(..., description="Module description")
    source_url: HttpUrl = Field(..., description="Source repository URL")
    downloads: int = Field(..., ge=0, description="Download count")
    verified: bool = Field(..., description="Verification status")
    published_at: datetime = Field(..., description="Publication date")


class ModuleSearchResponse(BaseModel):
    """Response model for module search."""

    query: str = Field(..., description="Original search query")
    total_found: int = Field(..., ge=0, description="Total modules found")
    modules: list[ModuleInfo] = Field(..., description="Module results")


class ModuleDetailsRequest(BaseModel):
    """Request model for module details."""

    module_id: str = Field(
        ..., description="Full module identifier (with or without version)"
    )


class ModuleInput(BaseModel):
    """Module input variable definition."""

    name: str = Field(..., description="Variable name")
    type: str = Field(..., description="Variable type")
    description: str = Field(..., description="Variable description")
    default: Any | None = Field(None, description="Default value")
    required: bool = Field(..., description="Whether variable is required")


class ModuleOutput(BaseModel):
    """Module output value definition."""

    name: str = Field(..., description="Output name")
    type: str = Field(..., description="Output type")
    description: str = Field(..., description="Output description")


class ModuleDependency(BaseModel):
    """Module dependency definition."""

    name: str = Field(..., description="Dependency name")
    version: str = Field(..., description="Version constraint")


class ListContentRequest(BaseModel):
    """Request model for listing repository content."""

    module_id: str = Field(
        ..., description="Full module identifier (with or without version)"
    )


class ContentPath(BaseModel):
    """Repository content path information."""

    path: str = Field(..., description="Path string")
    description: str = Field(..., description="Path description from README")
    type: str = Field(
        ..., description="Path type (root, examples, submodules, solutions)"
    )


class ListContentResponse(BaseModel):
    """Response model for listing repository content."""

    module_id: str = Field(..., description="Module identifier")
    version: str = Field(..., description="Scanned version")
    paths: list[ContentPath] = Field(..., description="Available content paths")


class GetContentRequest(BaseModel):
    """Request model for getting repository content."""

    module_id: str = Field(
        ..., description="Full module identifier (with or without version)"
    )
    path: str = Field("", description="Specific path to fetch")
    include_files: list[str] | None = Field(
        None, description="Glob patterns for files to include (e.g., '*.tf', '**/*.md')"
    )
    exclude_files: list[str] | None = Field(
        None,
        description="Glob patterns for files to exclude (e.g., '*test*', 'examples/**')",
    )


class FileContent(BaseModel):
    """File content information."""

    path: str = Field(..., description="File path")
    content: str = Field(..., description="File content")
    size: int = Field(..., ge=0, description="File size in bytes")


class GetContentResponse(BaseModel):
    """Response model for getting repository content."""

    module_id: str = Field(..., description="Module identifier")
    path: str = Field(..., description="Fetched path")
    version: str = Field(..., description="Fetched version")
    description: str | None = Field(None, description="Path description")
    files: list[FileContent] = Field(..., description="File contents")


class ErrorDetail(BaseModel):
    """Error detail information."""

    code: str = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    details: dict[str, Any] | None = Field(None, description="Additional details")


class ProviderSearchRequest(BaseModel):
    """Request model for provider search."""

    query: str | None = Field(
        None, description="Optional search term to filter providers"
    )
    limit: int = Field(10, ge=1, le=100, description="Maximum results to return")
    offset: int = Field(0, ge=0, description="Pagination offset")


class ProviderInfo(BaseModel):
    """Provider information from registry."""

    id: str = Field(..., description="Full provider identifier")
    namespace: str = Field(..., description="Provider namespace")
    name: str = Field(..., description="Provider name")
    version: str = Field(..., description="Latest version")
    description: str = Field(..., description="Provider description")
    source_url: HttpUrl = Field(..., description="Source repository URL")
    downloads: int = Field(..., ge=0, description="Download count")
    tier: str = Field(..., description="Provider tier (official, partner, community)")
    published_at: datetime = Field(..., description="Publication date")


class ProviderSearchResponse(BaseModel):
    """Response model for provider search."""

    query: str | None = Field(None, description="Original search query")
    total_found: int = Field(..., ge=0, description="Total providers in result")
    limit: int = Field(..., description="Results limit")
    offset: int = Field(..., description="Results offset")
    providers: list[ProviderInfo] = Field(..., description="Provider results")


class ProviderDetailsRequest(BaseModel):
    """Request model for provider details."""

    provider_id: str = Field(
        ...,
        min_length=1,
        description="Provider identifier (namespace/name or namespace/name/version)",
    )


class SearchProviderResourcesRequest(BaseModel):
    """Request model for searching provider resources and data sources."""

    provider_id: str = Field(
        default="IBM-Cloud/ibm",
        description="Provider identifier (namespace/name or namespace/name/version)",
    )
    query: str = Field(
        ..., min_length=1, description="Search keyword (e.g., 'vpc', 'security group')"
    )
    category: str | None = Field(
        None,
        description="Filter by category: 'resources', 'data-sources', or None for both",
    )
    subcategory: str | None = Field(
        None, description="Filter by subcategory (e.g., 'VPC', 'IAM')"
    )
    limit: int = Field(
        20, ge=1, le=50, description="Maximum results to return (default: 20)"
    )


class ProviderResourceSearchResult(BaseModel):
    """Individual search result for provider resource/data source."""

    provider_doc_id: str = Field(..., description="Provider document ID")
    slug: str = Field(..., description="Resource slug")
    title: str = Field(..., description="Resource title")
    category: str = Field(..., description="Category (resources or data-sources)")
    subcategory: str = Field(..., description="Subcategory grouping")
    description: str = Field(..., description="Brief description")
    relevance_score: int = Field(..., ge=0, description="Relevance score (0-100)")
    match_reasons: list[str] = Field(..., description="Reasons for match")


class SearchProviderResourcesResponse(BaseModel):
    """Response model for searching provider resources."""

    provider_id: str = Field(..., description="Provider identifier")
    provider_version: str = Field(..., description="Provider version")
    query: str = Field(..., description="Search query")
    category: str | None = Field(None, description="Category filter applied")
    subcategory: str | None = Field(None, description="Subcategory filter applied")
    total_found: int = Field(..., ge=0, description="Total matching results")
    returned: int = Field(..., ge=0, description="Number of results returned")
    results: list[ProviderResourceSearchResult] = Field(
        ..., description="Search results"
    )


class GetProviderResourceDetailsRequest(BaseModel):
    """Request model for getting provider resource details."""

    provider_doc_id: str = Field(..., description="Provider document ID from search")
    format: str = Field(
        default="full",
        description="Response format: 'full', 'examples', or 'schema'",
    )


class ProviderResourceArgument(BaseModel):
    """Provider resource argument definition."""

    name: str = Field(..., description="Argument name")
    type: str = Field(..., description="Argument type")
    required: bool = Field(..., description="Whether argument is required")
    description: str = Field(..., description="Argument description")
    default: Any | None = Field(None, description="Default value if any")


class ProviderResourceAttribute(BaseModel):
    """Provider resource attribute definition."""

    name: str = Field(..., description="Attribute name")
    type: str = Field(..., description="Attribute type")
    description: str = Field(..., description="Attribute description")


class ProviderResourceExample(BaseModel):
    """Provider resource example code."""

    title: str = Field(..., description="Example title")
    code: str = Field(..., description="Example HCL code")
    description: str | None = Field(None, description="Example description")


class RelatedResource(BaseModel):
    """Related provider resource reference."""

    slug: str = Field(..., description="Related resource slug")
    title: str = Field(..., description="Related resource title")


class ProviderResourceDetails(BaseModel):
    """Detailed provider resource/data source information."""

    provider_doc_id: str = Field(..., description="Provider document ID")
    slug: str = Field(..., description="Resource slug")
    title: str = Field(..., description="Resource title")
    category: str = Field(..., description="Category (resources or data-sources)")
    subcategory: str = Field(..., description="Subcategory grouping")
    provider_namespace: str = Field(..., description="Provider namespace")
    provider_name: str = Field(..., description="Provider name")
    provider_version: str = Field(..., description="Provider version")
    description: str = Field(..., description="Resource description")
    arguments: list[ProviderResourceArgument] = Field(
        ..., description="Resource arguments"
    )
    attributes: list[ProviderResourceAttribute] = Field(
        ..., description="Resource attributes"
    )
    examples: list[ProviderResourceExample] = Field(..., description="Usage examples")
    full_markdown: str | None = Field(None, description="Original markdown content")
    related_resources: list[RelatedResource] = Field(
        default_factory=list, description="Related resources"
    )
    documentation_url: str = Field(..., description="Documentation URL")
