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
        # Build cache key
        cache_key = f"list_all_modules_{namespace}"

        # Check cache first (with shorter TTL since this is comprehensive)
        cached = self.cache.get(cache_key)
        if cached:
            log_cache_operation(self.logger, "get", cache_key, hit=True)
            return cached

        log_cache_operation(self.logger, "get", cache_key, hit=False)

        all_modules = []
        offset = 0
        limit = 100  # Max per page
        max_pages = 20  # Safety limit to prevent infinite loops

        for page in range(max_pages):
            start_time = time.time()

            try:
                # Use namespace as the query term (workaround for API not supporting namespace-only filtering)
                params = {"q": namespace, "limit": limit, "offset": offset}
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

                modules = data.get("modules", [])
                if not modules:
                    # No more modules
                    break

                all_modules.extend(modules)

                # Log progress
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

                # Continue to next page if we got a full page
                # (total_count in meta is currently buggy and returns 0, so we rely on empty results)
                if len(modules) < limit:
                    # Got less than a full page, we're done
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

        # Cache the complete result
        self.cache.set(cache_key, all_modules)
        log_cache_operation(self.logger, "set", cache_key)

        self.logger.info(
            f"Successfully fetched all modules from namespace {namespace}",
            total_modules=len(all_modules),
        )

        return all_modules

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

            # Extract versions
            versions = [
                v.get("version") for v in data.get("modules", []) if v.get("version")
            ]

            # Log successful request
            log_api_request(
                self.logger,
                "GET",
                str(response.url),
                response.status_code,
                duration_ms,
                module_id=f"{namespace}/{name}/{provider}",
                version_count=len(versions),
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

            # Log successful request
            log_api_request(
                self.logger,
                "GET",
                str(response.url),
                response.status_code,
                duration_ms,
                provider_id=f"{namespace}/{name}",
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
