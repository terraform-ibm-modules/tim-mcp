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

    module_id: str = Field(..., description="Full module identifier (with or without version)")


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

    module_id: str = Field(..., description="Full module identifier (with or without version)")


class ContentPath(BaseModel):
    """Repository content path information."""

    path: str = Field(..., description="Path string")
    description: str = Field(..., description="Path description from README")
    type: str = Field(
        ..., description="Path type (root, examples, submodules)"
    )


class ListContentResponse(BaseModel):
    """Response model for listing repository content."""

    module_id: str = Field(..., description="Module identifier")
    version: str = Field(..., description="Scanned version")
    paths: list[ContentPath] = Field(..., description="Available content paths")


class GetExampleDetailsRequest(BaseModel):
    """Request model for getting example details."""

    module_id: str = Field(..., description="Full module identifier (with or without version)")
    example_path: str = Field(..., description="Example path (e.g., 'examples/basic')")


class GetContentRequest(BaseModel):
    """Request model for getting repository content."""

    module_id: str = Field(..., description="Full module identifier (with or without version)")
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
