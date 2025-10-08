"""
Async Terraform client for TIM-MCP.

This module provides an async client for interacting with the Terraform Registry API
with retry logic, caching, and comprehensive error handling.
"""

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
from ..logging import get_logger, log_api_request, log_cache_operation
from ..utils.cache import Cache
from ..utils.version import filter_stable_versions


class TerraformClient:
    """Async client for interacting with Terraform Registry API."""

    def __init__(self, config: Config, cache: Cache | None = None):
        """
        Initialize the Terraform client.

        Args:
            config: Configuration instance
            cache: Cache instance, or None to create a new one
        """
        self.config = config
        self.cache = cache or Cache(ttl=config.cache_ttl)
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
        # Build cache key
        cache_key = f"module_search_{query}_{namespace}_{limit}_{offset}"

        # Check cache first
        cached = self.cache.get(cache_key)
        if cached:
            log_cache_operation(self.logger, "get", cache_key, hit=True)
            return cached

        log_cache_operation(self.logger, "get", cache_key, hit=False)

        # Build query parameters
        params = {"q": query, "limit": limit, "offset": offset}
        if namespace:
            params["namespace"] = namespace

        start_time = time.time()

        try:
            response = await self.client.get("/modules/search", params=params)
            duration_ms = (time.time() - start_time) * 1000

            # Handle rate limiting
            if response.status_code == 429:
                reset_time = response.headers.get("X-RateLimit-Reset")
                raise RateLimitError(
                    "Terraform Registry rate limit exceeded",
                    reset_time=int(reset_time) if reset_time else None,
                    api_name="Terraform Registry",
                )

            response.raise_for_status()
            data = response.json()

            # Log successful request
            log_api_request(
                self.logger,
                "GET",
                str(response.url),
                response.status_code,
                duration_ms,
                query=query,
                result_count=len(data.get("modules", [])),
            )

            # Cache the result
            self.cache.set(cache_key, data)
            log_cache_operation(self.logger, "set", cache_key)

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
        # Build cache key
        cache_key = f"module_details_{namespace}_{name}_{provider}_{version}"

        # Check cache first
        cached = self.cache.get(cache_key)
        if cached:
            log_cache_operation(self.logger, "get", cache_key, hit=True)
            return cached

        log_cache_operation(self.logger, "get", cache_key, hit=False)

        start_time = time.time()

        try:
            url = f"/modules/{namespace}/{name}/{provider}"
            if version != "latest":
                url += f"/{version}"

            response = await self.client.get(url)
            duration_ms = (time.time() - start_time) * 1000

            # Handle rate limiting
            if response.status_code == 429:
                reset_time = response.headers.get("X-RateLimit-Reset")
                raise RateLimitError(
                    "Terraform Registry rate limit exceeded",
                    reset_time=int(reset_time) if reset_time else None,
                    api_name="Terraform Registry",
                )

            response.raise_for_status()
            data = response.json()

            # Log successful request
            log_api_request(
                self.logger,
                "GET",
                str(response.url),
                response.status_code,
                duration_ms,
                module_id=f"{namespace}/{name}/{provider}",
                version=version,
            )

            # Cache the result
            self.cache.set(cache_key, data)
            log_cache_operation(self.logger, "set", cache_key)

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
        # Build cache key
        cache_key = f"module_versions_{namespace}_{name}_{provider}"

        # Check cache first
        cached = self.cache.get(cache_key)
        if cached:
            log_cache_operation(self.logger, "get", cache_key, hit=True)
            return cached

        log_cache_operation(self.logger, "get", cache_key, hit=False)

        start_time = time.time()

        try:
            response = await self.client.get(
                f"/modules/{namespace}/{name}/{provider}/versions"
            )
            duration_ms = (time.time() - start_time) * 1000

            # Handle rate limiting
            if response.status_code == 429:
                reset_time = response.headers.get("X-RateLimit-Reset")
                raise RateLimitError(
                    "Terraform Registry rate limit exceeded",
                    reset_time=int(reset_time) if reset_time else None,
                    api_name="Terraform Registry",
                )

            response.raise_for_status()
            data = response.json()

            # Extract versions from nested structure
            # API returns: { "modules": [ { "versions": [ { "version": "1.0.0" }, ... ] } ] }
            all_versions = [
                v.get("version")
                for module in data.get("modules", [])
                for v in module.get("versions", [])
                if v.get("version")
            ]

            # Filter to only stable versions (exclude pre-release versions)
            versions = filter_stable_versions(all_versions)

            # Log successful request
            log_api_request(
                self.logger,
                "GET",
                str(response.url),
                response.status_code,
                duration_ms,
                module_id=f"{namespace}/{name}/{provider}",
                version_count=len(versions),
                filtered_count=len(all_versions) - len(versions),
            )

            # Cache the result
            self.cache.set(cache_key, versions)
            log_cache_operation(self.logger, "set", cache_key)

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
        # Build cache key
        cache_key = f"provider_info_{namespace}_{name}"

        # Check cache first
        cached = self.cache.get(cache_key)
        if cached:
            log_cache_operation(self.logger, "get", cache_key, hit=True)
            return cached

        log_cache_operation(self.logger, "get", cache_key, hit=False)

        start_time = time.time()

        try:
            response = await self.client.get(f"/providers/{namespace}/{name}")
            duration_ms = (time.time() - start_time) * 1000

            # Handle rate limiting
            if response.status_code == 429:
                reset_time = response.headers.get("X-RateLimit-Reset")
                raise RateLimitError(
                    "Terraform Registry rate limit exceeded",
                    reset_time=int(reset_time) if reset_time else None,
                    api_name="Terraform Registry",
                )

            response.raise_for_status()
            data = response.json()

            # Filter versions list to only stable versions if present
            if "versions" in data and isinstance(data["versions"], list):
                all_versions = data["versions"]
                stable_versions = filter_stable_versions(all_versions)
                data["versions"] = stable_versions
                filtered_count = len(all_versions) - len(stable_versions)
            else:
                filtered_count = 0

            # Log successful request
            log_api_request(
                self.logger,
                "GET",
                str(response.url),
                response.status_code,
                duration_ms,
                provider_id=f"{namespace}/{name}",
                filtered_count=filtered_count,
            )

            # Cache the result
            self.cache.set(cache_key, data)
            log_cache_operation(self.logger, "set", cache_key)

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

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
    )
    async def search_providers(
        self,
        query: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> dict[str, Any]:
        """
        Search for providers in the Terraform Registry.

        Args:
            query: Optional search query to filter providers
            limit: Maximum results to return
            offset: Offset for pagination

        Returns:
            Search results with providers and metadata

        Raises:
            TerraformRegistryError: If the API request fails
            RateLimitError: If rate limited
        """
        # Build cache key
        cache_key = f"provider_search_{query}_{limit}_{offset}"

        # Check cache first
        cached = self.cache.get(cache_key)
        if cached:
            log_cache_operation(self.logger, "get", cache_key, hit=True)
            return cached

        log_cache_operation(self.logger, "get", cache_key, hit=False)

        # Build query parameters
        params = {"limit": limit, "offset": offset}
        if query:
            params["q"] = query

        start_time = time.time()

        try:
            response = await self.client.get("/providers", params=params)
            duration_ms = (time.time() - start_time) * 1000

            # Handle rate limiting
            if response.status_code == 429:
                reset_time = response.headers.get("X-RateLimit-Reset")
                raise RateLimitError(
                    "Terraform Registry rate limit exceeded",
                    reset_time=int(reset_time) if reset_time else None,
                    api_name="Terraform Registry",
                )

            response.raise_for_status()
            data = response.json()

            # Log successful request
            log_api_request(
                self.logger,
                "GET",
                str(response.url),
                response.status_code,
                duration_ms,
                query=query,
                result_count=len(data.get("providers", [])),
            )

            # Cache the result
            self.cache.set(cache_key, data)
            log_cache_operation(self.logger, "set", cache_key)

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
                f"HTTP error searching providers: {e}",
                status_code=e.response.status_code,
                response_body=e.response.text,
            ) from e

        except httpx.RequestError as e:
            duration_ms = (time.time() - start_time) * 1000
            self.logger.error("Request error searching providers", error=str(e))
            raise TerraformRegistryError(
                f"Request error searching providers: {e}"
            ) from e

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
    )
    async def get_provider_details(
        self, namespace: str, name: str, version: str = "latest"
    ) -> dict[str, Any]:
        """
        Get detailed information about a specific provider version.

        Args:
            namespace: Provider namespace
            name: Provider name
            version: Provider version (default: "latest")

        Returns:
            Provider details including versions list

        Raises:
            TerraformRegistryError: If the API request fails
            RateLimitError: If rate limited
        """
        # Build cache key
        cache_key = f"provider_details_{namespace}_{name}_{version}"

        # Check cache first
        cached = self.cache.get(cache_key)
        if cached:
            log_cache_operation(self.logger, "get", cache_key, hit=True)
            return cached

        log_cache_operation(self.logger, "get", cache_key, hit=False)

        start_time = time.time()

        try:
            # Build URL - API returns latest version if no version specified
            url = f"/providers/{namespace}/{name}"
            if version != "latest":
                url += f"/{version}"

            response = await self.client.get(url)
            duration_ms = (time.time() - start_time) * 1000

            # Handle rate limiting
            if response.status_code == 429:
                reset_time = response.headers.get("X-RateLimit-Reset")
                raise RateLimitError(
                    "Terraform Registry rate limit exceeded",
                    reset_time=int(reset_time) if reset_time else None,
                    api_name="Terraform Registry",
                )

            response.raise_for_status()
            data = response.json()

            # Filter versions list to only stable versions if present
            if "versions" in data and isinstance(data["versions"], list):
                all_versions = data["versions"]
                stable_versions = filter_stable_versions(all_versions)
                data["versions"] = stable_versions
                filtered_count = len(all_versions) - len(stable_versions)
            else:
                filtered_count = 0

            # Log successful request
            log_api_request(
                self.logger,
                "GET",
                str(response.url),
                response.status_code,
                duration_ms,
                provider_id=f"{namespace}/{name}",
                version=version,
                filtered_count=filtered_count,
            )

            # Cache the result
            self.cache.set(cache_key, data)
            log_cache_operation(self.logger, "set", cache_key)

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
                f"HTTP error getting provider details: {e}",
                status_code=e.response.status_code,
                response_body=e.response.text,
            ) from e

        except httpx.RequestError as e:
            duration_ms = (time.time() - start_time) * 1000
            self.logger.error("Request error getting provider details", error=str(e))
            raise TerraformRegistryError(
                f"Request error getting provider details: {e}"
            ) from e

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
    )
    async def get_provider_version_id(
        self, namespace: str, name: str, version: str = "latest"
    ) -> str:
        """
        Get the numeric version ID for a provider version.

        This is needed to query the v2 provider-docs API.

        Args:
            namespace: Provider namespace
            name: Provider name
            version: Provider version (default: "latest")

        Returns:
            Numeric version ID as string

        Raises:
            TerraformRegistryError: If the API request fails
            RateLimitError: If rate limited
        """
        # Build cache key
        cache_key = f"provider_version_id_{namespace}_{name}_{version}"

        # Check cache first
        cached = self.cache.get(cache_key)
        if cached:
            log_cache_operation(self.logger, "get", cache_key, hit=True)
            return cached

        log_cache_operation(self.logger, "get", cache_key, hit=False)

        start_time = time.time()

        try:
            # First get the provider ID from v2 API
            provider_response = await self.client.get(
                f"https://registry.terraform.io/v2/providers/{namespace}/{name}"
            )
            duration_ms = (time.time() - start_time) * 1000

            # Handle rate limiting
            if provider_response.status_code == 429:
                reset_time = provider_response.headers.get("X-RateLimit-Reset")
                raise RateLimitError(
                    "Terraform Registry rate limit exceeded",
                    reset_time=int(reset_time) if reset_time else None,
                    api_name="Terraform Registry",
                )

            provider_response.raise_for_status()
            provider_data = provider_response.json()
            provider_id = provider_data["data"]["id"]

            # Get all versions for this provider
            versions_response = await self.client.get(
                f"https://registry.terraform.io/v2/providers/{provider_id}/provider-versions"
            )
            versions_response.raise_for_status()
            versions_data = versions_response.json()

            # Find the matching version or get the latest
            if version == "latest":
                # Get the most recent version by published date
                latest_version = max(
                    versions_data["data"],
                    key=lambda v: v["attributes"]["published-at"],
                )
                version_id = latest_version["id"]
            else:
                # Find exact version match
                for v in versions_data["data"]:
                    if v["attributes"]["version"] == version:
                        version_id = v["id"]
                        break
                else:
                    raise TerraformRegistryError(
                        f"Version {version} not found for provider {namespace}/{name}",
                        status_code=404,
                    )

            # Log successful request
            duration_ms = (time.time() - start_time) * 1000
            log_api_request(
                self.logger,
                "GET",
                f"/providers/{namespace}/{name}/versions",
                200,
                duration_ms,
                provider_id=f"{namespace}/{name}",
                version=version,
                version_id=version_id,
            )

            # Cache the result
            self.cache.set(cache_key, version_id)
            log_cache_operation(self.logger, "set", cache_key)

            return version_id

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
                f"HTTP error getting provider version ID: {e}",
                status_code=e.response.status_code,
                response_body=e.response.text,
            ) from e

        except httpx.RequestError as e:
            duration_ms = (time.time() - start_time) * 1000
            self.logger.error("Request error getting provider version ID", error=str(e))
            raise TerraformRegistryError(
                f"Request error getting provider version ID: {e}"
            ) from e

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
    )
    async def list_provider_docs(
        self,
        provider_version_id: str,
        category: str | None = None,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        """
        List all documentation entries for a provider version.

        Args:
            provider_version_id: Numeric provider version ID
            category: Optional category filter ('resources', 'data-sources')
            page_size: Number of results per page (default: 100)

        Returns:
            List of documentation entries with metadata

        Raises:
            TerraformRegistryError: If the API request fails
            RateLimitError: If rate limited
        """
        # Build cache key
        cache_key = f"provider_docs_{provider_version_id}_{category}_{page_size}"

        # Check cache first
        cached = self.cache.get(cache_key)
        if cached:
            log_cache_operation(self.logger, "get", cache_key, hit=True)
            return cached

        log_cache_operation(self.logger, "get", cache_key, hit=False)

        start_time = time.time()
        all_docs = []

        try:
            # Build query parameters
            params = {
                "filter[provider-version]": provider_version_id,
                "page[size]": page_size,
            }
            if category:
                params["filter[category]"] = category

            # Fetch all pages
            page_number = 1
            while True:
                params["page[number]"] = page_number

                response = await self.client.get(
                    "https://registry.terraform.io/v2/provider-docs", params=params
                )

                # Handle rate limiting
                if response.status_code == 429:
                    reset_time = response.headers.get("X-RateLimit-Reset")
                    raise RateLimitError(
                        "Terraform Registry rate limit exceeded",
                        reset_time=int(reset_time) if reset_time else None,
                        api_name="Terraform Registry",
                    )

                response.raise_for_status()
                data = response.json()

                docs = data.get("data", [])
                all_docs.extend(docs)

                # Check if there are more pages
                if len(docs) < page_size:
                    break

                page_number += 1

            # Log successful request
            duration_ms = (time.time() - start_time) * 1000
            log_api_request(
                self.logger,
                "GET",
                "/provider-docs",
                200,
                duration_ms,
                provider_version_id=provider_version_id,
                category=category,
                doc_count=len(all_docs),
            )

            # Cache the result
            self.cache.set(cache_key, all_docs)
            log_cache_operation(self.logger, "set", cache_key)

            return all_docs

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
                f"HTTP error listing provider docs: {e}",
                status_code=e.response.status_code,
                response_body=e.response.text,
            ) from e

        except httpx.RequestError as e:
            duration_ms = (time.time() - start_time) * 1000
            self.logger.error("Request error listing provider docs", error=str(e))
            raise TerraformRegistryError(
                f"Request error listing provider docs: {e}"
            ) from e

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
    )
    async def get_provider_doc_content(self, doc_id: str) -> dict[str, Any]:
        """
        Get the full markdown content for a specific provider documentation entry.

        Args:
            doc_id: Provider documentation ID

        Returns:
            Documentation entry with full content

        Raises:
            TerraformRegistryError: If the API request fails
            RateLimitError: If rate limited
        """
        # Build cache key
        cache_key = f"provider_doc_content_{doc_id}"

        # Check cache first
        cached = self.cache.get(cache_key)
        if cached:
            log_cache_operation(self.logger, "get", cache_key, hit=True)
            return cached

        log_cache_operation(self.logger, "get", cache_key, hit=False)

        start_time = time.time()

        try:
            response = await self.client.get(
                f"https://registry.terraform.io/v2/provider-docs/{doc_id}"
            )

            # Handle rate limiting
            if response.status_code == 429:
                reset_time = response.headers.get("X-RateLimit-Reset")
                raise RateLimitError(
                    "Terraform Registry rate limit exceeded",
                    reset_time=int(reset_time) if reset_time else None,
                    api_name="Terraform Registry",
                )

            response.raise_for_status()
            data = response.json()

            # Log successful request
            duration_ms = (time.time() - start_time) * 1000
            log_api_request(
                self.logger,
                "GET",
                f"/provider-docs/{doc_id}",
                200,
                duration_ms,
                doc_id=doc_id,
            )

            # Cache the result
            self.cache.set(cache_key, data)
            log_cache_operation(self.logger, "set", cache_key)

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
                f"HTTP error getting provider doc content: {e}",
                status_code=e.response.status_code,
                response_body=e.response.text,
            ) from e

        except httpx.RequestError as e:
            duration_ms = (time.time() - start_time) * 1000
            self.logger.error(
                "Request error getting provider doc content", error=str(e)
            )
            raise TerraformRegistryError(
                f"Request error getting provider doc content: {e}"
            ) from e
