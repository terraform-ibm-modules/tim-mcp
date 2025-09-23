"""
Configuration for TIM-MCP.

This module handles environment variables and configuration settings
for the TIM-MCP server.
"""

import os

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from .exceptions import ConfigurationError


class Config(BaseModel):
    """Configuration model for TIM-MCP."""

    # GitHub Configuration
    github_token: str | None = Field(None, description="GitHub API token for authenticated requests")
    github_base_url: HttpUrl = Field(
        default_factory=lambda: HttpUrl("https://api.github.com"),
        description="GitHub API base URL",
    )

    # Terraform Registry Configuration
    terraform_registry_url: HttpUrl = Field(
        default_factory=lambda: HttpUrl("https://registry.terraform.io/v1"),
        description="Terraform Registry API URL",
    )

    # Cache Configuration
    cache_ttl: int = Field(3600, ge=60, description="Cache TTL in seconds")
    cache_dir: str | None = Field(None, description="Cache directory path")

    # Request Configuration
    request_timeout: int = Field(30, ge=1, description="Request timeout in seconds")
    max_retries: int = Field(3, ge=0, description="Maximum retry attempts")
    retry_backoff: float = Field(1.0, ge=0.1, description="Retry backoff factor")

    # Rate Limiting
    respect_rate_limits: bool = Field(True, description="Whether to respect API rate limits")

    # Logging
    log_level: str = Field("INFO", description="Logging level")
    structured_logging: bool = Field(True, description="Use structured logging")

    # Filtering Configuration
    allowed_namespaces: list[str] = Field(
        default_factory=lambda: ["terraform-ibm-modules"], description="List of allowed module namespaces to search within"
    )
    excluded_modules: list[str] = Field(default_factory=list, description="List of module IDs to exclude from search results")

    model_config = ConfigDict(env_prefix="TIM_")


def load_config() -> Config:
    """
    Load configuration from environment variables.

    Returns:
        Configured Config instance

    Raises:
        ConfigurationError: If configuration is invalid
    """
    try:
        # Override defaults with environment variables
        config_data = {}

        # GitHub configuration
        if github_token := os.getenv("GITHUB_TOKEN"):
            config_data["github_token"] = github_token

        if github_base_url := os.getenv("TIM_GITHUB_BASE_URL"):
            config_data["github_base_url"] = github_base_url

        # Terraform Registry configuration
        if terraform_registry_url := os.getenv("TIM_TERRAFORM_REGISTRY_URL"):
            config_data["terraform_registry_url"] = terraform_registry_url

        # Cache configuration
        if cache_ttl := os.getenv("TIM_CACHE_TTL"):
            config_data["cache_ttl"] = int(cache_ttl)

        if cache_dir := os.getenv("TIM_CACHE_DIR"):
            config_data["cache_dir"] = cache_dir

        # Request configuration
        if request_timeout := os.getenv("TIM_REQUEST_TIMEOUT"):
            config_data["request_timeout"] = int(request_timeout)

        if max_retries := os.getenv("TIM_MAX_RETRIES"):
            config_data["max_retries"] = int(max_retries)

        if retry_backoff := os.getenv("TIM_RETRY_BACKOFF"):
            config_data["retry_backoff"] = float(retry_backoff)

        # Rate limiting
        if respect_rate_limits := os.getenv("TIM_RESPECT_RATE_LIMITS"):
            config_data["respect_rate_limits"] = respect_rate_limits.lower() == "true"

        # Logging
        if log_level := os.getenv("TIM_LOG_LEVEL"):
            config_data["log_level"] = log_level.upper()

        if structured_logging := os.getenv("TIM_STRUCTURED_LOGGING"):
            config_data["structured_logging"] = structured_logging.lower() == "true"

        # Filtering configuration
        if allowed_namespaces := os.getenv("TIM_ALLOWED_NAMESPACES"):
            config_data["allowed_namespaces"] = [ns.strip() for ns in allowed_namespaces.split(",")]

        if excluded_modules := os.getenv("TIM_EXCLUDED_MODULES"):
            config_data["excluded_modules"] = [mod.strip() for mod in excluded_modules.split(",")]

        return Config(**config_data)

    except ValueError as e:
        raise ConfigurationError(f"Invalid configuration: {e}") from e


def get_github_auth_headers(config: Config) -> dict[str, str]:
    """
    Get GitHub authentication headers.

    Args:
        config: Configuration instance

    Returns:
        Dictionary of headers for GitHub API requests
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "TIM-MCP/0.1.0",
    }

    if config.github_token:
        headers["Authorization"] = f"Bearer {config.github_token}"

    return headers


def get_terraform_registry_headers() -> dict[str, str]:
    """
    Get Terraform Registry headers.

    Returns:
        Dictionary of headers for Terraform Registry API requests
    """
    return {
        "Accept": "application/json",
        "User-Agent": "TIM-MCP/0.1.0",
    }
