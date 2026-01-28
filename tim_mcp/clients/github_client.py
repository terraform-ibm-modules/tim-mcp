"""
Async GitHub client for TIM-MCP.

Provides an async client for interacting with the GitHub API with retry logic,
caching, and comprehensive error handling. Supports GitHub.com and GitHub
Enterprise.
"""

import base64
import time
from typing import Any

import httpx

from ..config import Config, get_github_auth_headers
from ..exceptions import GitHubError, ModuleNotFoundError
from ..logging import get_logger, log_api_request
from ..utils.cache import InMemoryCache
from ..utils.rate_limiter import RateLimiter
from .base import api_method, check_rate_limit_response


class GitHubClient:
    """Async client for interacting with GitHub API."""

    def __init__(
        self,
        config: Config,
        cache: InMemoryCache | None = None,
        rate_limiter: RateLimiter | None = None,
    ):
        """
        Initialize the GitHub client.

        Args:
            config: Configuration instance
            cache: Cache instance, or None to create a new one
            rate_limiter: Rate limiter instance for request throttling
        """
        self.config = config
        self.cache = cache or InMemoryCache(
            fresh_ttl=config.cache_fresh_ttl,
            evict_ttl=config.cache_evict_ttl,
            maxsize=config.cache_maxsize,
        )
        self.rate_limiter = rate_limiter
        self.logger = get_logger(__name__, client="github")

        headers = get_github_auth_headers(config)
        self.client = httpx.AsyncClient(
            base_url=str(config.github_base_url),
            timeout=config.request_timeout,
            headers=headers,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    async def _get_with_etag(
        self,
        url: str,
        cache_key: str,
        params: dict | None = None,
    ) -> tuple[httpx.Response | None, Any | None, bool]:
        """
        Make GET request with ETag validation support.

        Returns:
            Tuple of (response, cached_data, was_not_modified)
            - On 304: (None, cached_data, True)
            - On other response: (response, None, False)
        """
        headers = {}
        cached_data = None

        if self.cache:
            etag = self.cache.get_etag(cache_key)
            if etag:
                headers["If-None-Match"] = etag
                cached_data = self.cache.get(cache_key, allow_stale=True)

        response = await self.client.get(url, params=params, headers=headers)

        if response.status_code == 304 and cached_data is not None:
            if self.cache:
                new_etag = response.headers.get("ETag")
                self.cache.refresh(cache_key, etag=new_etag)
            self.logger.debug("ETag cache hit (304)", cache_key=cache_key)
            return None, cached_data, True

        return response, None, False

    def _store_with_etag(
        self, cache_key: str, data: Any, response: httpx.Response
    ) -> None:
        """Store data in cache with ETag from response headers."""
        if self.cache:
            etag = response.headers.get("ETag")
            self.cache.set(cache_key, data, etag=etag)

    def _parse_module_id(self, module_id: str) -> tuple[str, str, str]:
        """Parse module ID into namespace, name, provider components."""
        parts = module_id.split("/")
        if len(parts) != 3:
            raise ModuleNotFoundError(
                module_id, details={"reason": "Invalid module ID format"}
            )
        return parts[0], parts[1], parts[2]

    def _extract_repo_from_module_id(self, module_id: str) -> tuple[str, str]:
        """Extract GitHub repository owner and name from module ID."""
        namespace, name, provider = self._parse_module_id(module_id)
        if namespace == "terraform-ibm-modules":
            repo_name = f"terraform-ibm-{name}"
        else:
            repo_name = f"terraform-{name}-{provider}"
        return namespace, repo_name

    def parse_github_url(self, source_url: str) -> tuple[str, str] | None:
        """Parse GitHub URL to extract owner and repository name."""
        from urllib.parse import urlparse

        if not source_url:
            return None

        clean_url = source_url[5:] if source_url.startswith("git::") else source_url

        try:
            parsed = urlparse(clean_url)
            if parsed.netloc not in ["github.com", "www.github.com"]:
                return None

            path = parsed.path.strip("/")
            if path.endswith(".git"):
                path = path[:-4]

            path_parts = path.split("/")
            if len(path_parts) < 2:
                return None

            return path_parts[0], path_parts[1]
        except Exception as e:
            self.logger.warning(
                "Failed to parse GitHub URL", url=source_url, error=str(e)
            )
            return None

    @api_method(cache_key_prefix=None)  # Caching handled manually for ETag support
    async def get_repository_info(self, owner: str, repo: str) -> dict[str, Any]:
        """Get repository information."""
        start_time = time.time()
        cache_key = f"gh_repo_info_{owner}_{repo}"

        try:
            if self.cache:
                cached = self.cache.get(cache_key, allow_stale=False)
                if cached is not None:
                    return cached

            response, cached_data, not_modified = await self._get_with_etag(
                f"/repos/{owner}/{repo}", cache_key
            )

            if not_modified:
                return cached_data

            check_rate_limit_response(response, "GitHub")
            response.raise_for_status()

            duration_ms = (time.time() - start_time) * 1000
            data = response.json()
            self._store_with_etag(cache_key, data, response)

            log_api_request(
                self.logger,
                "GET",
                str(response.url),
                response.status_code,
                duration_ms,
                repo=f"{owner}/{repo}",
            )
            return data

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ModuleNotFoundError(
                    f"{owner}/{repo}", details={"reason": "Repository not found"}
                ) from e
            raise GitHubError(
                f"HTTP error getting repository info: {e}",
                status_code=e.response.status_code,
                response_body=e.response.text,
            ) from e
        except httpx.RequestError as e:
            raise GitHubError(f"Request error getting repository info: {e}") from e

    @api_method(cache_key_prefix=None)  # Caching handled manually for ETag support
    async def get_directory_contents(
        self, owner: str, repo: str, path: str = "", ref: str = "HEAD"
    ) -> list[dict[str, Any]]:
        """Get directory contents from repository."""
        start_time = time.time()
        cache_key = f"gh_dir_contents_{owner}_{repo}_{path}_ref={ref}"
        params = {"ref": ref} if ref != "HEAD" else {}
        url = (
            f"/repos/{owner}/{repo}/contents/{path}"
            if path
            else f"/repos/{owner}/{repo}/contents"
        )

        try:
            if self.cache:
                cached = self.cache.get(cache_key, allow_stale=False)
                if cached is not None:
                    return cached

            response, cached_data, not_modified = await self._get_with_etag(
                url, cache_key, params=params if params else None
            )

            if not_modified:
                return cached_data

            check_rate_limit_response(response, "GitHub")
            response.raise_for_status()

            duration_ms = (time.time() - start_time) * 1000
            data = response.json()
            if not isinstance(data, list):
                data = [data]

            self._store_with_etag(cache_key, data, response)

            log_api_request(
                self.logger,
                "GET",
                str(response.url),
                response.status_code,
                duration_ms,
                repo=f"{owner}/{repo}",
                path=path,
                item_count=len(data),
            )
            return data

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return []
            raise GitHubError(
                f"HTTP error getting directory contents: {e}",
                status_code=e.response.status_code,
                response_body=e.response.text,
            ) from e
        except httpx.RequestError as e:
            raise GitHubError(f"Request error getting directory contents: {e}") from e

    @api_method(cache_key_prefix=None)  # Caching handled manually for ETag support
    async def get_file_content(
        self, owner: str, repo: str, path: str, ref: str = "HEAD"
    ) -> dict[str, Any]:
        """Get file content from repository."""
        start_time = time.time()
        cache_key = f"gh_file_content_{owner}_{repo}_{path}_ref={ref}"
        params = {"ref": ref} if ref != "HEAD" else {}
        url = f"/repos/{owner}/{repo}/contents/{path}"

        try:
            if self.cache:
                cached = self.cache.get(cache_key, allow_stale=False)
                if cached is not None:
                    return cached

            response, cached_data, not_modified = await self._get_with_etag(
                url, cache_key, params=params if params else None
            )

            if not_modified:
                return cached_data

            check_rate_limit_response(response, "GitHub")
            response.raise_for_status()

            duration_ms = (time.time() - start_time) * 1000
            data = response.json()
            if data.get("encoding") == "base64" and data.get("content"):
                try:
                    data["decoded_content"] = base64.b64decode(data["content"]).decode(
                        "utf-8"
                    )
                except Exception as e:
                    self.logger.warning("Failed to decode base64 content", error=str(e))

            self._store_with_etag(cache_key, data, response)

            log_api_request(
                self.logger,
                "GET",
                str(response.url),
                response.status_code,
                duration_ms,
                repo=f"{owner}/{repo}",
                path=path,
                size=data.get("size", 0),
            )
            return data

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ModuleNotFoundError(
                    f"{owner}/{repo}/{path}", details={"reason": "File not found"}
                ) from e
            raise GitHubError(
                f"HTTP error getting file content: {e}",
                status_code=e.response.status_code,
                response_body=e.response.text,
            ) from e
        except httpx.RequestError as e:
            raise GitHubError(f"Request error getting file content: {e}") from e

    @api_method(cache_key_prefix=None)  # Caching handled manually for ETag support
    async def get_repository_tree(
        self, owner: str, repo: str, ref: str = "HEAD", recursive: bool = True
    ) -> list[dict[str, Any]]:
        """Get repository tree (all files and directories)."""
        start_time = time.time()
        cache_key = f"gh_repo_tree_{owner}_{repo}_{ref}_{recursive}"
        params = {"recursive": "1"} if recursive else {}
        url = f"/repos/{owner}/{repo}/git/trees/{ref}"

        try:
            if self.cache:
                cached = self.cache.get(cache_key, allow_stale=False)
                if cached is not None:
                    return cached

            response, cached_data, not_modified = await self._get_with_etag(
                url, cache_key, params=params
            )

            if not_modified:
                return cached_data

            check_rate_limit_response(response, "GitHub")
            response.raise_for_status()

            duration_ms = (time.time() - start_time) * 1000
            tree_items = response.json().get("tree", [])
            self._store_with_etag(cache_key, tree_items, response)

            log_api_request(
                self.logger,
                "GET",
                str(response.url),
                response.status_code,
                duration_ms,
                repo=f"{owner}/{repo}",
                tree_size=len(tree_items),
            )
            return tree_items

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ModuleNotFoundError(
                    f"{owner}/{repo}",
                    details={"reason": "Repository or reference not found"},
                ) from e
            raise GitHubError(
                f"HTTP error getting repository tree: {e}",
                status_code=e.response.status_code,
                response_body=e.response.text,
            ) from e
        except httpx.RequestError as e:
            raise GitHubError(f"Request error getting repository tree: {e}") from e

    def match_file_patterns(
        self,
        file_path: str,
        include_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
    ) -> bool:
        """Check if file matches include/exclude glob patterns."""
        from pathlib import Path

        path = Path(file_path)
        if exclude_patterns:
            for pattern in exclude_patterns:
                if path.match(pattern):
                    return False
        if include_patterns:
            return any(path.match(pattern) for pattern in include_patterns)
        return True

    def clone_repository(
        self, repo_url: str, target_dir: str, branch: str | None = None
    ) -> bool:
        """Clone a GitHub repository."""
        try:
            import os
            import subprocess

            cmd = ["git", "clone"]
            if branch:
                cmd.extend(["-b", branch])
            cmd.extend([repo_url, target_dir])
            os.makedirs(os.path.dirname(target_dir), exist_ok=True)
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            self.logger.info(
                f"Successfully cloned repository {repo_url} to {target_dir}",
                branch=branch,
            )
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(
                f"Failed to clone repository {repo_url}", error=str(e), stderr=e.stderr
            )
            return False
        except Exception as e:
            self.logger.error(
                f"Unexpected error cloning repository {repo_url}", error=str(e)
            )
            return False

    async def get_content(
        self, owner: str, repo: str, path: str, ref: str | None = None
    ) -> dict[str, Any]:
        """Get content from a repository (wrapper around get_file_content)."""
        return await self.get_file_content(owner, repo, path, ref or "HEAD")

    @api_method(cache_key_prefix="gh_latest_release")
    async def get_latest_release(self, owner: str, repo: str) -> dict[str, Any]:
        """Get the latest release for a repository."""
        start_time = time.time()
        try:
            response = await self.client.get(f"/repos/{owner}/{repo}/releases/latest")
            duration_ms = (time.time() - start_time) * 1000
            check_rate_limit_response(response, "GitHub")
            response.raise_for_status()

            data = response.json()
            log_api_request(
                self.logger,
                "GET",
                str(response.url),
                response.status_code,
                duration_ms,
                repo=f"{owner}/{repo}",
                tag_name=data.get("tag_name"),
            )
            return data

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ModuleNotFoundError(
                    f"{owner}/{repo}", details={"reason": "No releases found"}
                ) from e
            raise GitHubError(
                f"HTTP error getting latest release: {e}",
                status_code=e.response.status_code,
                response_body=e.response.text,
            ) from e
        except httpx.RequestError as e:
            raise GitHubError(f"Request error getting latest release: {e}") from e

    @api_method(cache_key_prefix="gh_resolve_version")
    async def resolve_version(
        self, owner: str, repo: str, version: str = "latest"
    ) -> str:
        """Resolve version to actual git reference."""
        if version != "latest":
            return version

        try:
            release_data = await self.get_latest_release(owner, repo)
            resolved = release_data.get("tag_name", "HEAD")
            self.logger.info(
                "Resolved latest version to release tag",
                repo=f"{owner}/{repo}",
                resolved_version=resolved,
            )
            return resolved
        except ModuleNotFoundError:
            self.logger.warning(
                "No releases found, falling back to HEAD", repo=f"{owner}/{repo}"
            )
            return "HEAD"
        except Exception as e:
            self.logger.warning(
                "Failed to resolve latest version, falling back to HEAD",
                repo=f"{owner}/{repo}",
                error=str(e),
            )
            return "HEAD"
