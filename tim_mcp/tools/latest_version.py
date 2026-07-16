"""Latest module version lookup tool for TIM-MCP."""

from typing import Any

from ..clients.github_client import GitHubClient
from ..clients.terraform_client import TerraformClient
from ..config import Config
from ..context import get_cache, get_rate_limiter
from ..exceptions import ModuleNotFoundError, TerraformRegistryError, ValidationError
from ..utils.module_id import parse_module_id_with_version


def _get_repo_name(namespace: str, name: str, provider: str) -> str:
    """Build the GitHub repository name for a module."""
    if namespace == "terraform-ibm-modules":
        return f"terraform-ibm-{name}"
    return f"terraform-{name}-{provider}"


def format_latest_module_version(
    module_id: str, latest_version: str, release_data: dict[str, Any] | None = None
) -> str:
    """Format latest module version information as markdown."""
    lines = [
        f"# {module_id} - Latest Version",
        "",
        f"**Latest Version:** v{latest_version}",
    ]

    if release_data:
        lines.extend(
            [
                f"**Release Tag:** {release_data.get('tag_name', 'N/A')}",
                f"**Release Name:** {release_data.get('name') or release_data.get('tag_name') or 'N/A'}",
                f"**Published:** {(release_data.get('published_at') or 'N/A')[:10] if release_data.get('published_at') else 'N/A'}",
                f"**Release URL:** {release_data.get('html_url', 'N/A')}",
            ]
        )

        if release_data.get("body"):
            lines.extend(["", "## Release Notes", release_data["body"].strip()])
    else:
        lines.extend(["**Release Information:** Not available"]) 

    return "\n".join(lines)


async def get_latest_module_version_impl(
    request, config: Config
) -> str:
    """Implementation for latest module version lookup."""
    try:
        namespace, name, provider, _ = parse_module_id_with_version(request.module_id)
    except ValidationError as e:
        raise TerraformRegistryError(f"Module ID validation failed: {e}") from e

    cache = get_cache()
    rate_limiter = get_rate_limiter()

    async with TerraformClient(
        config, cache=cache, rate_limiter=rate_limiter
    ) as terraform_client:
        versions = await terraform_client.get_module_versions(
            namespace=namespace,
            name=name,
            provider=provider,
        )

    if not versions:
        raise ModuleNotFoundError(request.module_id)

    latest_version = versions[0]
    release_data = None

    async with GitHubClient(config, cache=cache, rate_limiter=rate_limiter) as github_client:
        try:
            release_data = await github_client.get_latest_release(
                owner=namespace,
                repo=_get_repo_name(namespace, name, provider),
            )
        except ModuleNotFoundError:
            release_data = None

    return format_latest_module_version(
        f"{namespace}/{name}/{provider}",
        latest_version,
        release_data,
    )
