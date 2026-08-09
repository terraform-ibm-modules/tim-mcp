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


class SubmoduleSummary(BaseModel):
    """Brief submodule information for module listing."""

    path: str = Field(..., description="Submodule path within the repository")
    name: str = Field(..., description="Submodule name")
    description: str = Field(
        default="", description="Submodule description extracted from README"
    )
    source_url: str = Field(
        ..., description="GitHub source URL for the submodule directory"
    )


class ModuleListItem(BaseModel):
    """Module list item with category and key information."""

    module_id: str = Field(..., description="Full module identifier")
    name: str = Field(..., description="Module name")
    description: str = Field(..., description="Module description")
    category: str = Field(
        ..., description="Module category (e.g., networking, security, compute)"
    )
    submodules: list[SubmoduleSummary] = Field(
        default_factory=list, description="Available submodules"
    )
    latest_version: str = Field(..., description="Latest version")
    downloads: int = Field(..., ge=0, description="Download count")
    source_url: HttpUrl = Field(..., description="Source repository URL")
    published_at: datetime = Field(..., description="Publication date")


class ModuleListResponse(BaseModel):
    """Response model for listing all modules."""

    total_count: int = Field(..., ge=0, description="Total modules returned")
    modules: list[ModuleListItem] = Field(
        ..., description="All modules ordered by downloads"
    )


class ModuleDetailsRequest(BaseModel):
    """Request model for module details."""

    module_id: str = Field(
        ..., description="Full module identifier (with or without version)"
    )


class LatestModuleVersionRequest(BaseModel):
    """Request model for latest module version lookup."""

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
    type: str = Field(..., description="Path type (root, examples, submodules)")


class ListContentResponse(BaseModel):
    """Response model for listing repository content."""

    module_id: str = Field(..., description="Module identifier")
    version: str = Field(..., description="Scanned version")
    paths: list[ContentPath] = Field(..., description="Available content paths")


class GetExampleDetailsRequest(BaseModel):
    """Request model for getting example details."""

    module_id: str = Field(
        ..., description="Full module identifier (with or without version)"
    )
    example_path: str = Field(..., description="Example path (e.g., 'examples/basic')")


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


class SubmoduleInfo(BaseModel):
    """Submodule information from module details."""

    path: str = Field(..., description="Submodule path within the repository")
    name: str = Field(..., description="Submodule name")
    readme: str | None = Field(None, description="Submodule README content")
    inputs: list[ModuleInput] = Field(
        default_factory=list, description="Submodule inputs"
    )
    outputs: list[ModuleOutput] = Field(
        default_factory=list, description="Submodule outputs"
    )


class ListSubmodulesRequest(BaseModel):
    """Request model for listing submodules."""

    module_id: str = Field(
        ..., description="Full module identifier (e.g., terraform-ibm-modules/cbr/ibm)"
    )


class ListSubmodulesResponse(BaseModel):
    """Response model for listing submodules."""

    module_id: str = Field(..., description="Module identifier")
    version: str = Field(..., description="Module version")
    total_count: int = Field(..., ge=0, description="Total submodules found")
    submodules: list[SubmoduleInfo] = Field(..., description="Submodule information")


class ErrorDetail(BaseModel):
    """Error detail information."""

    code: str = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    details: dict[str, Any] | None = Field(None, description="Additional details")


class GenerateModuleCompositionRequest(BaseModel):
    """Request model for generating a module composition suggestion."""

    service_or_pattern: str = Field(
        ...,
        min_length=1,
        description=(
            "A service name, architecture keyword, or composition name to build "
            "a stack around (e.g. 'openshift', 'postgresql', 'watsonx', "
            "'event streams', or the exact composition name 'vpc-landing-zone')."
        ),
    )
    environment: str | None = Field(
        None,
        description=(
            "Optional target environment to bias selection: 'production' or "
            "'development'. Defaults to no preference."
        ),
    )


class RecommendedModule(BaseModel):
    """A module recommended as part of a composition."""

    id: str = Field(..., description="Base module identifier (namespace/name/provider)")
    instance_name: str = Field(
        ..., description="Suggested Terraform module block name for this instance"
    )
    role: str = Field(
        "core",
        description=(
            "Provenance/role of the module in the stack: 'core' (composed by the "
            "anchor DA), 'prerequisite' (infra the DA expects to already exist, "
            "provisioned here for an end-to-end stack), or 'optional' (add-on the "
            "DA does not include)."
        ),
    )
    purpose: str = Field(..., description="Why this module is part of the composition")
    version: str | None = Field(
        None, description="Latest known module version, resolved from the module index"
    )
    source: str = Field(
        ..., description="Terraform Registry source to use in the module block"
    )
    registry_url: str | None = Field(
        None, description="Terraform Registry URL for the module"
    )


class ModuleConnection(BaseModel):
    """A wiring between two modules (an output feeding an input)."""

    source_module: str = Field(
        ..., description="Instance name of the module producing the value"
    )
    source_output: str = Field(..., description="Output name on the source module")
    target_module: str = Field(
        ..., description="Instance name of the module consuming the value"
    )
    target_input: str = Field(
        ..., description="Input variable name on the target module"
    )
    note: str | None = Field(
        None, description="Optional guidance on how to apply this connection"
    )


class CompositionPrerequisite(BaseModel):
    """An input the consumer must supply for the whole composition."""

    name: str = Field(..., description="Prerequisite name")
    type: str = Field(..., description="Prerequisite type (e.g. secret, string)")
    required: bool = Field(..., description="Whether the prerequisite is required")
    description: str | None = Field(None, description="What the prerequisite is for")


class ReferenceSolution(BaseModel):
    """Pointer to the Deployable Architecture solution a composition is anchored on."""

    module_id: str = Field(
        ..., description="Base module ID whose repository holds the DA solution"
    )
    solution_path: str = Field(
        ...,
        description="Path to the solution within the repo (e.g. solutions/fully-configurable)",
    )
    source_url: str = Field(..., description="GitHub URL of the DA solution directory")
    fetch_hint: str | None = Field(
        None,
        description=(
            "Suggested get_content call to retrieve the ground-truth DA wiring "
            "(module_id resolved with its latest version)."
        ),
    )


class ModuleComposition(BaseModel):
    """A full architecture composition recommendation."""

    composition_name: str = Field(..., description="Unique composition identifier")
    display_name: str = Field(..., description="Human-readable composition name")
    description: str = Field(..., description="What the composition builds")
    category: str = Field(..., description="Architecture category")
    environment: str = Field(
        ..., description="Environment the composition targets (e.g. production)"
    )
    reference_solution: ReferenceSolution | None = Field(
        None,
        description="The Deployable Architecture solution this composition is anchored on",
    )
    recommended_modules: list[RecommendedModule] = Field(
        ..., description="Modules that make up the stack"
    )
    deployment_order: list[str] = Field(
        ..., description="Instance names in recommended deployment order"
    )
    connections: list[ModuleConnection] = Field(
        ..., description="How module outputs wire into other module inputs"
    )
    prerequisites: list[CompositionPrerequisite] = Field(
        ..., description="Inputs the consumer must supply"
    )
    notes: list[str] = Field(
        default_factory=list, description="Additional guidance for the composition"
    )


class CompositionSummary(BaseModel):
    """Brief description of an available composition."""

    composition_name: str = Field(..., description="Unique composition identifier")
    display_name: str = Field(..., description="Human-readable composition name")
    category: str = Field(..., description="Architecture category")
    environment: str = Field(..., description="Environment the composition targets")
    services: list[str] = Field(
        ..., description="Services/keywords this composition matches"
    )


class GenerateModuleCompositionResponse(BaseModel):
    """Response model for a module composition suggestion."""

    matched: bool = Field(
        ..., description="Whether a composition matched the requested pattern"
    )
    query: str = Field(..., description="The original service_or_pattern query")
    composition: ModuleComposition | None = Field(
        None, description="The best-matching composition, if any"
    )
    alternatives: list[CompositionSummary] = Field(
        default_factory=list,
        description="Other compositions that also matched the query",
    )
    available_compositions: list[CompositionSummary] = Field(
        default_factory=list,
        description="All available compositions (populated when nothing matched)",
    )
    message: str | None = Field(
        None, description="Human-readable guidance about the result"
    )
