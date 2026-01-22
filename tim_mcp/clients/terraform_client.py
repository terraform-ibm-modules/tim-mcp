"""
Async Terraform client for TIM-MCP.

This module provides an async client for interacting with the Terraform Registry API
with retry logic, caching, and comprehensive error handling.
"""

import re
import time
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..config import Config, get_terraform_registry_headers
from ..exceptions import RateLimitError, TerraformRegistryError
from ..logging import get_logger, log_api_request
from ..utils.cache import InMemoryCache
from ..utils.rate_limiter import RateLimiter, with_rate_limit


# Cache key generators - centralized to ensure consistency
def _cache_key_module_search(
    _self: Any,
    query: str,
    namespace: str | None = None,
    limit: int = 10,
    offset: int = 0,
) -> str:
    return f"module_search_{query}_{namespace}_{limit}_{offset}"


def _cache_key_list_all_modules(_self: Any, namespace: str) -> str:
    return f"list_all_modules_{namespace}"


def _cache_key_module_details(
    _self: Any, namespace: str, name: str, provider: str, version: str = "latest"
) -> str:
    return f"module_details_{namespace}_{name}_{provider}_{version}"


def _cache_key_module_versions(
    _self: Any, namespace: str, name: str, provider: str
) -> str:
    return f"module_versions_{namespace}_{name}_{provider}"


def _cache_key_provider_info(_self: Any, namespace: str, name: str) -> str:
    return f"provider_info_{namespace}_{name}"


def is_prerelease_version(version: str) -> bool:
    """
    Check if a version string is a pre-release version.

    Pre-release versions contain identifiers like:
    - beta, alpha, rc (release candidate)
    - draft, dev, pre
    - Any version with a hyphen followed by additional identifiers

    Examples:
        - "2.0.1-beta" -> True
        - "2.0.1-draft-addons" -> True
        - "1.0.0-rc.1" -> True
        - "2.0.1" -> False
        - "1.2.3" -> False

    Args:
        version: Version string to check

    Returns:
        True if the version is a pre-release, False otherwise
    """
    # Pattern matches semantic versions with pre-release identifiers
    # Format: X.Y.Z-<prerelease>
    prerelease_pattern = r"^\d+\.\d+\.\d+-"
    return bool(re.match(prerelease_pattern, version))


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

        # Configure HTTP client
        self.client = httpx.AsyncClient(
            base_url=str(config.terraform_registry_url),
            timeout=config.request_timeout,
            headers=get_terraform_registry_headers(),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.client.aclose()

    @with_rate_limit(
        limiter_getter=lambda self: self.rate_limiter,
        cache_getter=lambda self: self.cache,
        cache_key_fn=_cache_key_module_search,
    )
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
    )
    async def search_modules(
        self,
        query: str,
        namespace: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> dict[str, Any]:
        """
        Search for modules in the Terraform Registry.

        Args:
            query: Search query
            namespace: Optional namespace to filter by
            limit: Maximum results to return
            offset: Offset for pagination

        Returns:
            Search results with modules and metadata

        Raises:
            TerraformRegistryError: If the API request fails
            RateLimitError: If rate limited
        """
        params = {"q": query, "limit": limit, "offset": offset}
        if namespace:
            params["namespace"] = namespace

        start_time = time.time()

        try:
            response = await self.client.get("/modules/search", params=params)
            duration_ms = (time.time() - start_time) * 1000

            if response.status_code == 429:
                reset_time = response.headers.get("X-RateLimit-Reset")
                raise RateLimitError(
                    "Terraform Registry rate limit exceeded",
                    reset_time=int(reset_time) if reset_time else None,
                    api_name="Terraform Registry",
                )

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
            duration_ms = (time.time() - start_time) * 1000
            log_api_request(
                self.logger,
                "GET",
                str(e.request.url),
                e.response.status_code,
                duration_ms,
                error=str(e),
            )
            raise TerraformRegistryError(
                f"HTTP error searching modules: {e}",
                status_code=e.response.status_code,
                response_body=e.response.text,
            ) from e

        except httpx.RequestError as e:
            duration_ms = (time.time() - start_time) * 1000
            self.logger.error("Request error searching modules", error=str(e))
            raise TerraformRegistryError(f"Request error searching modules: {e}") from e

    @with_rate_limit(
        limiter_getter=lambda self: self.rate_limiter,
        cache_getter=lambda self: self.cache,
        cache_key_fn=_cache_key_list_all_modules,
    )
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
    )
    async def list_all_modules(
        self,
        namespace: str,
    ) -> list[dict[str, Any]]:
        """
        List all modules in a namespace by fetching all pages.

        Args:
            namespace: Namespace to list modules from

        Returns:
            List of all modules in the namespace

        Raises:
            TerraformRegistryError: If the API request fails
            RateLimitError: If rate limited
        """
        all_modules = []
        offset = 0
        limit = 100  # Max per page
        max_pages = 20  # Safety limit to prevent infinite loops

        for page in range(max_pages):
            start_time = time.time()

            try:
                params = {"namespace": namespace, "limit": limit, "offset": offset}
                response = await self.client.get("/modules", params=params)
                duration_ms = (time.time() - start_time) * 1000

                if response.status_code == 429:
                    reset_time = response.headers.get("X-RateLimit-Reset")
                    raise RateLimitError(
                        "Terraform Registry rate limit exceeded",
                        reset_time=int(reset_time) if reset_time else None,
                        api_name="Terraform Registry",
                    )

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
                duration_ms = (time.time() - start_time) * 1000
                log_api_request(
                    self.logger,
                    "GET",
                    str(e.request.url),
                    e.response.status_code,
                    duration_ms,
                    error=str(e),
                )
                raise TerraformRegistryError(
                    f"HTTP error listing modules: {e}",
                    status_code=e.response.status_code,
                    response_body=e.response.text,
                ) from e

            except httpx.RequestError as e:
                duration_ms = (time.time() - start_time) * 1000
                self.logger.error("Request error listing modules", error=str(e))
                raise TerraformRegistryError(
                    f"Request error listing modules: {e}"
                ) from e

        self.logger.info(
            f"Successfully fetched all modules from namespace {namespace}",
            total_modules=len(all_modules),
        )

        return all_modules

    @with_rate_limit(
        limiter_getter=lambda self: self.rate_limiter,
        cache_getter=lambda self: self.cache,
        cache_key_fn=_cache_key_module_details,
    )
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
    )
    async def get_module_details(
        self, namespace: str, name: str, provider: str, version: str = "latest"
    ) -> dict[str, Any]:
        """
        Get detailed information about a specific module.

        Args:
            namespace: Module namespace
            name: Module name
            provider: Module provider
            version: Module version

        Returns:
            Module details including inputs, outputs, dependencies

        Raises:
            TerraformRegistryError: If the API request fails
            RateLimitError: If rate limited
        """
        start_time = time.time()

        try:
            url = f"/modules/{namespace}/{name}/{provider}"
            if version != "latest":
                url += f"/{version}"

            response = await self.client.get(url)
            duration_ms = (time.time() - start_time) * 1000

            if response.status_code == 429:
                reset_time = response.headers.get("X-RateLimit-Reset")
                raise RateLimitError(
                    "Terraform Registry rate limit exceeded",
                    reset_time=int(reset_time) if reset_time else None,
                    api_name="Terraform Registry",
                )

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
            duration_ms = (time.time() - start_time) * 1000
            log_api_request(
                self.logger,
                "GET",
                str(e.request.url),
                e.response.status_code,
                duration_ms,
                error=str(e),
            )
            raise TerraformRegistryError(
                f"HTTP error getting module details: {e}",
                status_code=e.response.status_code,
                response_body=e.response.text,
            ) from e

        except httpx.RequestError as e:
            duration_ms = (time.time() - start_time) * 1000
            self.logger.error("Request error getting module details", error=str(e))
            raise TerraformRegistryError(
                f"Request error getting module details: {e}"
            ) from e

    @with_rate_limit(
        limiter_getter=lambda self: self.rate_limiter,
        cache_getter=lambda self: self.cache,
        cache_key_fn=_cache_key_module_versions,
    )
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
    )
    async def get_module_versions(
        self, namespace: str, name: str, provider: str
    ) -> list[str]:
        """
        Get available versions for a module.

        Args:
            namespace: Module namespace
            name: Module name
            provider: Module provider

        Returns:
            List of available versions

        Raises:
            TerraformRegistryError: If the API request fails
            RateLimitError: If rate limited
        """
        start_time = time.time()

        try:
            response = await self.client.get(
                f"/modules/{namespace}/{name}/{provider}/versions"
            )
            duration_ms = (time.time() - start_time) * 1000

            if response.status_code == 429:
                reset_time = response.headers.get("X-RateLimit-Reset")
                raise RateLimitError(
                    "Terraform Registry rate limit exceeded",
                    reset_time=int(reset_time) if reset_time else None,
                    api_name="Terraform Registry",
                )

            response.raise_for_status()
            data = response.json()

            # Extract versions from the nested structure
            # API returns: {"modules": [{"versions": [{"version": "1.0.0"}, ...]}]}
            modules = data.get("modules", [])
            if not modules:
                all_versions = []
            else:
                versions_list = modules[0].get("versions", [])
                all_versions = [
                    v.get("version") for v in versions_list if v.get("version")
                ]

            # Filter out pre-release versions (beta, alpha, rc, draft, etc.)
            versions = [v for v in all_versions if not is_prerelease_version(v)]

            # Sort versions in descending order (latest first) using semantic versioning
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
            duration_ms = (time.time() - start_time) * 1000
            log_api_request(
                self.logger,
                "GET",
                str(e.request.url),
                e.response.status_code,
                duration_ms,
                error=str(e),
            )
            raise TerraformRegistryError(
                f"HTTP error getting module versions: {e}",
                status_code=e.response.status_code,
                response_body=e.response.text,
            ) from e

        except httpx.RequestError as e:
            duration_ms = (time.time() - start_time) * 1000
            self.logger.error("Request error getting module versions", error=str(e))
            raise TerraformRegistryError(
                f"Request error getting module versions: {e}"
            ) from e

    @with_rate_limit(
        limiter_getter=lambda self: self.rate_limiter,
        cache_getter=lambda self: self.cache,
        cache_key_fn=_cache_key_provider_info,
    )
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
    )
    async def get_provider_info(self, namespace: str, name: str) -> dict[str, Any]:
        """
        Get information about a provider.

        Args:
            namespace: Provider namespace
            name: Provider name

        Returns:
            Provider information

        Raises:
            TerraformRegistryError: If the API request fails
            RateLimitError: If rate limited
        """
        start_time = time.time()

        try:
            response = await self.client.get(f"/providers/{namespace}/{name}")
            duration_ms = (time.time() - start_time) * 1000

            if response.status_code == 429:
                reset_time = response.headers.get("X-RateLimit-Reset")
                raise RateLimitError(
                    "Terraform Registry rate limit exceeded",
                    reset_time=int(reset_time) if reset_time else None,
                    api_name="Terraform Registry",
                )

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
            duration_ms = (time.time() - start_time) * 1000
            log_api_request(
                self.logger,
                "GET",
                str(e.request.url),
                e.response.status_code,
                duration_ms,
                error=str(e),
            )
            raise TerraformRegistryError(
                f"HTTP error getting provider info: {e}",
                status_code=e.response.status_code,
                response_body=e.response.text,
            ) from e

        except httpx.RequestError as e:
            duration_ms = (time.time() - start_time) * 1000
            self.logger.error("Request error getting provider info", error=str(e))
            raise TerraformRegistryError(
                f"Request error getting provider info: {e}"
            ) from e
