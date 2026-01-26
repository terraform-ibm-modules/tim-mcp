"""
Async Terraform client for TIM-MCP.

Provides an async client for interacting with the Terraform Registry API
with retry logic, caching, and comprehensive error handling.
"""

import re
import time
from typing import Any

import httpx

from ..config import Config, get_terraform_registry_headers
from ..exceptions import TerraformRegistryError
from ..logging import get_logger, log_api_request
from ..utils.cache import InMemoryCache
from ..utils.rate_limiter import RateLimiter
from .base import api_method, check_rate_limit_response


def is_prerelease_version(version: str) -> bool:
    """Check if a version string is a pre-release version."""
    return bool(re.match(r"^\d+\.\d+\.\d+-", version))


class TerraformClient:
    """Async client for interacting with Terraform Registry API."""

    def __init__(
        self,
        config: Config,
        cache: InMemoryCache | None = None,
        rate_limiter: RateLimiter | None = None,
    ):
        """
        Initialize the Terraform client.

        Args:
            config: Configuration instance
            cache: Cache instance, or None to create a new one
            rate_limiter: Rate limiter instance for request throttling
        """
        self.config = config
        self.cache = cache or InMemoryCache(
            ttl=config.cache_ttl, maxsize=config.cache_maxsize
        )
        self.rate_limiter = rate_limiter
        self.logger = get_logger(__name__, client="terraform")

        self.client = httpx.AsyncClient(
            base_url=str(config.terraform_registry_url),
            timeout=config.request_timeout,
            headers=get_terraform_registry_headers(),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    @api_method(cache_key_prefix="tf_module_search")
    async def search_modules(
        self, query: str, namespace: str | None = None, limit: int = 10, offset: int = 0
    ) -> dict[str, Any]:
        """Search for modules in the Terraform Registry."""
        start_time = time.time()
        params = {"q": query, "limit": limit, "offset": offset}
        if namespace:
            params["namespace"] = namespace

        try:
            response = await self.client.get("/modules/search", params=params)
            duration_ms = (time.time() - start_time) * 1000
            check_rate_limit_response(response, "Terraform Registry")
            response.raise_for_status()

            data = response.json()
            log_api_request(
                self.logger,
                "GET",
                str(response.url),
                response.status_code,
                duration_ms,
                query=query,
                result_count=len(data.get("modules", [])),
            )
            return data

        except httpx.HTTPStatusError as e:
            raise TerraformRegistryError(
                f"HTTP error searching modules: {e}",
                status_code=e.response.status_code,
                response_body=e.response.text,
            ) from e
        except httpx.RequestError as e:
            raise TerraformRegistryError(f"Request error searching modules: {e}") from e

    @api_method(cache_key_prefix="tf_list_modules")
    async def list_all_modules(self, namespace: str) -> list[dict[str, Any]]:
        """List all modules in a namespace by fetching all pages."""
        all_modules = []
        offset = 0
        limit = 100
        max_pages = 20

        for page in range(max_pages):
            start_time = time.time()
            try:
                params = {"namespace": namespace, "limit": limit, "offset": offset}
                response = await self.client.get("/modules", params=params)
                duration_ms = (time.time() - start_time) * 1000
                check_rate_limit_response(response, "Terraform Registry")
                response.raise_for_status()

                data = response.json()
                modules = data.get("modules", [])
                if not modules:
                    break

                all_modules.extend(modules)
                log_api_request(
                    self.logger,
                    "GET",
                    str(response.url),
                    response.status_code,
                    duration_ms,
                    namespace=namespace,
                    page=page + 1,
                    modules_in_page=len(modules),
                    total_so_far=len(all_modules),
                )

                if len(modules) < limit:
                    break
                offset += limit

            except httpx.HTTPStatusError as e:
                raise TerraformRegistryError(
                    f"HTTP error listing modules: {e}",
                    status_code=e.response.status_code,
                    response_body=e.response.text,
                ) from e
            except httpx.RequestError as e:
                raise TerraformRegistryError(
                    f"Request error listing modules: {e}"
                ) from e

        self.logger.info(
            f"Successfully fetched all modules from namespace {namespace}",
            total_modules=len(all_modules),
        )
        return all_modules

    @api_method(cache_key_prefix="tf_module_details")
    async def get_module_details(
        self, namespace: str, name: str, provider: str, version: str = "latest"
    ) -> dict[str, Any]:
        """Get detailed information about a specific module."""
        start_time = time.time()
        try:
            url = f"/modules/{namespace}/{name}/{provider}"
            if version != "latest":
                url += f"/{version}"

            response = await self.client.get(url)
            duration_ms = (time.time() - start_time) * 1000
            check_rate_limit_response(response, "Terraform Registry")
            response.raise_for_status()

            data = response.json()
            log_api_request(
                self.logger,
                "GET",
                str(response.url),
                response.status_code,
                duration_ms,
                module_id=f"{namespace}/{name}/{provider}",
                version=version,
            )
            return data

        except httpx.HTTPStatusError as e:
            raise TerraformRegistryError(
                f"HTTP error getting module details: {e}",
                status_code=e.response.status_code,
                response_body=e.response.text,
            ) from e
        except httpx.RequestError as e:
            raise TerraformRegistryError(
                f"Request error getting module details: {e}"
            ) from e

    @api_method(cache_key_prefix="tf_module_versions")
    async def get_module_versions(
        self, namespace: str, name: str, provider: str
    ) -> list[str]:
        """Get available versions for a module."""
        start_time = time.time()
        try:
            response = await self.client.get(
                f"/modules/{namespace}/{name}/{provider}/versions"
            )
            duration_ms = (time.time() - start_time) * 1000
            check_rate_limit_response(response, "Terraform Registry")
            response.raise_for_status()

            data = response.json()
            modules = data.get("modules", [])
            if not modules:
                all_versions = []
            else:
                versions_list = modules[0].get("versions", [])
                all_versions = [
                    v.get("version") for v in versions_list if v.get("version")
                ]

            # Filter out pre-release versions
            versions = [v for v in all_versions if not is_prerelease_version(v)]

            # Sort versions (latest first)
            from packaging.version import InvalidVersion, Version

            try:
                versions.sort(key=lambda v: Version(v), reverse=True)
            except InvalidVersion:
                pass

            log_api_request(
                self.logger,
                "GET",
                str(response.url),
                response.status_code,
                duration_ms,
                module_id=f"{namespace}/{name}/{provider}",
                version_count=len(versions),
                total_versions=len(all_versions),
                filtered_count=len(all_versions) - len(versions),
            )
            return versions

        except httpx.HTTPStatusError as e:
            raise TerraformRegistryError(
                f"HTTP error getting module versions: {e}",
                status_code=e.response.status_code,
                response_body=e.response.text,
            ) from e
        except httpx.RequestError as e:
            raise TerraformRegistryError(
                f"Request error getting module versions: {e}"
            ) from e

    @api_method(cache_key_prefix="tf_provider_info")
    async def get_provider_info(self, namespace: str, name: str) -> dict[str, Any]:
        """Get information about a provider."""
        start_time = time.time()
        try:
            response = await self.client.get(f"/providers/{namespace}/{name}")
            duration_ms = (time.time() - start_time) * 1000
            check_rate_limit_response(response, "Terraform Registry")
            response.raise_for_status()

            data = response.json()
            log_api_request(
                self.logger,
                "GET",
                str(response.url),
                response.status_code,
                duration_ms,
                provider_id=f"{namespace}/{name}",
            )
            return data

        except httpx.HTTPStatusError as e:
            raise TerraformRegistryError(
                f"HTTP error getting provider info: {e}",
                status_code=e.response.status_code,
                response_body=e.response.text,
            ) from e
        except httpx.RequestError as e:
            raise TerraformRegistryError(
                f"Request error getting provider info: {e}"
            ) from e
