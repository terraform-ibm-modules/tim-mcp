"""
Async GitHub client for TIM-MCP.

This module provides an async client for interacting with the GitHub API
with retry logic, caching, and comprehensive error handling.
Supports both GitHub.com and GitHub Enterprise.
"""

import base64
import time
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..config import Config, get_github_auth_headers
from ..exceptions import GitHubError, ModuleNotFoundError, RateLimitError
from ..logging import get_logger, log_api_request, log_cache_operation
from ..utils.cache import Cache


class GitHubClient:
    """Async client for interacting with GitHub API."""

    def __init__(self, config: Config, cache: Cache | None = None):
        """
        Initialize the GitHub client.

        Args:
            config: Configuration instance
            cache: Cache instance, or None to create a new one
        """
        self.config = config
        self.cache = cache or Cache(ttl=config.cache_ttl)
        self.logger = get_logger(__name__, client="github")

        # Configure HTTP client
        headers = get_github_auth_headers(config)
        self.client = httpx.AsyncClient(
            base_url=str(config.github_base_url),
            timeout=config.request_timeout,
            headers=headers,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )

        # Track rate limits
        self.rate_limit_remaining = None
        self.rate_limit_reset = None

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.client.aclose()

    def _update_rate_limit_info(self, response: httpx.Response) -> None:
        """Update rate limit information from response headers."""
        self.rate_limit_remaining = response.headers.get("X-RateLimit-Remaining")
        self.rate_limit_reset = response.headers.get("X-RateLimit-Reset")

    def _parse_module_id(self, module_id: str) -> tuple[str, str, str]:
        """
        Parse module ID into namespace, name, provider components.

        Args:
            module_id: Module ID in format "namespace/name/provider"

        Returns:
            Tuple of (namespace, name, provider)

        Raises:
            ModuleNotFoundError: If module ID format is invalid
        """
        parts = module_id.split("/")
        if len(parts) != 3:
            raise ModuleNotFoundError(
                module_id, details={"reason": "Invalid module ID format"}
            )
        return parts[0], parts[1], parts[2]

    def _extract_repo_from_module_id(self, module_id: str) -> tuple[str, str]:
        """
        Extract GitHub repository owner and name from module ID.

        Args:
            module_id: Module ID in format "namespace/name/provider"

        Returns:
            Tuple of (owner, repo_name)
        """
        namespace, name, provider = self._parse_module_id(module_id)

        # For terraform-ibm-modules, the repo name is usually terraform-ibm-{name}
        if namespace == "terraform-ibm-modules":
            repo_name = f"terraform-ibm-{name}"
        else:
            # For other namespaces, try to construct the repo name
            repo_name = f"terraform-{name}-{provider}"

        return namespace, repo_name

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
    )
    async def get_repository_info(self, owner: str, repo: str) -> dict[str, Any]:
        """
        Get repository information.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            Repository information

        Raises:
            GitHubError: If the API request fails
            RateLimitError: If rate limited
        """
        cache_key = f"repo_info_{owner}_{repo}"

        # Check cache first
        cached = self.cache.get(cache_key)
        if cached:
            log_cache_operation(self.logger, "get", cache_key, hit=True)
            return cached

        log_cache_operation(self.logger, "get", cache_key, hit=False)

        start_time = time.time()

        try:
            response = await self.client.get(f"/repos/{owner}/{repo}")
            duration_ms = (time.time() - start_time) * 1000

            self._update_rate_limit_info(response)

            # Handle rate limiting
            if response.status_code == 429:
                raise RateLimitError(
                    "GitHub rate limit exceeded",
                    reset_time=int(self.rate_limit_reset)
                    if self.rate_limit_reset
                    else None,
                    api_name="GitHub",
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
                repo=f"{owner}/{repo}",
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
            if e.response.status_code == 404:
                raise ModuleNotFoundError(
                    f"{owner}/{repo}",
                    details={"reason": "Repository not found"},
                ) from e
            raise GitHubError(
                f"HTTP error getting repository info: {e}",
                status_code=e.response.status_code,
                response_body=e.response.text,
            ) from e

        except httpx.RequestError as e:
            duration_ms = (time.time() - start_time) * 1000
            self.logger.error("Request error getting repository info", error=str(e))
            raise GitHubError(f"Request error getting repository info: {e}") from e

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
    )
    async def get_directory_contents(
        self, owner: str, repo: str, path: str = "", ref: str = "HEAD"
    ) -> list[dict[str, Any]]:
        """
        Get directory contents from repository.

        Args:
            owner: Repository owner
            repo: Repository name
            path: Directory path
            ref: Git reference (branch, tag, commit)

        Returns:
            List of directory contents

        Raises:
            GitHubError: If the API request fails
            RateLimitError: If rate limited
        """
        cache_key = f"dir_contents_{owner}_{repo}_{path}_{ref}"

        # Check cache first
        cached = self.cache.get(cache_key)
        if cached:
            log_cache_operation(self.logger, "get", cache_key, hit=True)
            return cached

        log_cache_operation(self.logger, "get", cache_key, hit=False)

        start_time = time.time()

        try:
            params = {"ref": ref} if ref != "HEAD" else {}
            url = f"/repos/{owner}/{repo}/contents"
            if path:
                url += f"/{path}"

            response = await self.client.get(url, params=params)
            duration_ms = (time.time() - start_time) * 1000

            self._update_rate_limit_info(response)

            # Handle rate limiting
            if response.status_code == 429:
                raise RateLimitError(
                    "GitHub rate limit exceeded",
                    reset_time=int(self.rate_limit_reset)
                    if self.rate_limit_reset
                    else None,
                    api_name="GitHub",
                )

            response.raise_for_status()
            data = response.json()

            # Ensure we return a list
            if not isinstance(data, list):
                data = [data]

            # Log successful request
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
            if e.response.status_code == 404:
                return []  # Path doesn't exist, return empty list
            raise GitHubError(
                f"HTTP error getting directory contents: {e}",
                status_code=e.response.status_code,
                response_body=e.response.text,
            ) from e

        except httpx.RequestError as e:
            duration_ms = (time.time() - start_time) * 1000
            self.logger.error("Request error getting directory contents", error=str(e))
            raise GitHubError(f"Request error getting directory contents: {e}") from e

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
    )
    async def get_file_content(
        self, owner: str, repo: str, path: str, ref: str = "HEAD"
    ) -> dict[str, Any]:
        """
        Get file content from repository.

        Args:
            owner: Repository owner
            repo: Repository name
            path: File path
            ref: Git reference (branch, tag, commit)

        Returns:
            File content information

        Raises:
            GitHubError: If the API request fails
            RateLimitError: If rate limited
        """
        cache_key = f"file_content_{owner}_{repo}_{path}_{ref}"

        # Check cache first
        cached = self.cache.get(cache_key)
        if cached:
            log_cache_operation(self.logger, "get", cache_key, hit=True)
            return cached

        log_cache_operation(self.logger, "get", cache_key, hit=False)

        start_time = time.time()

        try:
            params = {"ref": ref} if ref != "HEAD" else {}
            response = await self.client.get(
                f"/repos/{owner}/{repo}/contents/{path}", params=params
            )
            duration_ms = (time.time() - start_time) * 1000

            self._update_rate_limit_info(response)

            # Handle rate limiting
            if response.status_code == 429:
                raise RateLimitError(
                    "GitHub rate limit exceeded",
                    reset_time=int(self.rate_limit_reset)
                    if self.rate_limit_reset
                    else None,
                    api_name="GitHub",
                )

            response.raise_for_status()
            data = response.json()

            # Decode content if it's base64 encoded
            if data.get("encoding") == "base64" and data.get("content"):
                try:
                    decoded_content = base64.b64decode(data["content"]).decode("utf-8")
                    data["decoded_content"] = decoded_content
                except Exception as e:
                    self.logger.warning("Failed to decode base64 content", error=str(e))

            # Log successful request
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
            if e.response.status_code == 404:
                raise ModuleNotFoundError(
                    f"{owner}/{repo}/{path}",
                    details={"reason": "File not found"},
                ) from e
            raise GitHubError(
                f"HTTP error getting file content: {e}",
                status_code=e.response.status_code,
                response_body=e.response.text,
            ) from e

        except httpx.RequestError as e:
            duration_ms = (time.time() - start_time) * 1000
            self.logger.error("Request error getting file content", error=str(e))
            raise GitHubError(f"Request error getting file content: {e}") from e

    async def get_repository_tree(
        self, owner: str, repo: str, ref: str = "HEAD", recursive: bool = True
    ) -> list[dict[str, Any]]:
        """
        Get repository tree (all files and directories).

        Args:
            owner: Repository owner
            repo: Repository name
            ref: Git reference (branch, tag, commit)
            recursive: Whether to get recursive tree

        Returns:
            List of tree items

        Raises:
            GitHubError: If the API request fails
            RateLimitError: If rate limited
        """
        cache_key = f"repo_tree_{owner}_{repo}_{ref}_{recursive}"

        # Check cache first
        cached = self.cache.get(cache_key)
        if cached:
            log_cache_operation(self.logger, "get", cache_key, hit=True)
            return cached

        log_cache_operation(self.logger, "get", cache_key, hit=False)

        start_time = time.time()

        try:
            params = {"recursive": "1"} if recursive else {}
            response = await self.client.get(
                f"/repos/{owner}/{repo}/git/trees/{ref}", params=params
            )
            duration_ms = (time.time() - start_time) * 1000

            self._update_rate_limit_info(response)

            # Handle rate limiting
            if response.status_code == 429:
                raise RateLimitError(
                    "GitHub rate limit exceeded",
                    reset_time=int(self.rate_limit_reset)
                    if self.rate_limit_reset
                    else None,
                    api_name="GitHub",
                )

            response.raise_for_status()
            data = response.json()
            tree_items = data.get("tree", [])

            # Log successful request
            log_api_request(
                self.logger,
                "GET",
                str(response.url),
                response.status_code,
                duration_ms,
                repo=f"{owner}/{repo}",
                tree_size=len(tree_items),
            )

            # Cache the result
            self.cache.set(cache_key, tree_items)
            log_cache_operation(self.logger, "set", cache_key)

            return tree_items

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
            duration_ms = (time.time() - start_time) * 1000
            self.logger.error("Request error getting repository tree", error=str(e))
            raise GitHubError(f"Request error getting repository tree: {e}") from e

    def match_file_patterns(
        self,
        file_path: str,
        include_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
    ) -> bool:
        """
        Check if file matches include/exclude glob patterns.

        Args:
            file_path: File path to check
            include_patterns: List of glob patterns to include (e.g., "*.tf", "**/*.md")
            exclude_patterns: List of glob patterns to exclude (e.g., "*test*", "examples/**")

        Returns:
            True if file should be included
        """
        from pathlib import Path

        path = Path(file_path)

        # Check exclude patterns first
        if exclude_patterns:
            for pattern in exclude_patterns:
                if path.match(pattern):
                    return False

        # Check include patterns
        if include_patterns:
            for pattern in include_patterns:
                if path.match(pattern):
                    return True
            # If we had include patterns but none matched, exclude the file
            return False

        return True  # No patterns specified, include by default

    def clone_repository(
        self, repo_url: str, target_dir: str, branch: str | None = None
    ) -> bool:
        """
        Clone a GitHub repository.

        Args:
            repo_url: Repository URL
            target_dir: Target directory
            branch: Optional branch to checkout

        Returns:
            True if successful, False otherwise
        """
        try:
            import os
            import subprocess

            # Build git clone command
            cmd = ["git", "clone"]
            if branch:
                cmd.extend(["-b", branch])
            cmd.extend([repo_url, target_dir])

            # Create parent directory if it doesn't exist
            os.makedirs(os.path.dirname(target_dir), exist_ok=True)

            # Run git clone
            subprocess.run(cmd, capture_output=True, text=True, check=True)

            self.logger.info(
                f"Successfully cloned repository {repo_url} to {target_dir}",
                branch=branch,
            )
            return True

        except subprocess.CalledProcessError as e:
            self.logger.error(
                f"Failed to clone repository {repo_url}",
                error=str(e),
                stderr=e.stderr,
            )
            return False
        except Exception as e:
            self.logger.error(
                f"Unexpected error cloning repository {repo_url}",
                error=str(e),
            )
            return False

    async def get_content(
        self, owner: str, repo: str, path: str, ref: str | None = None
    ) -> dict[str, Any]:
        """
        Get content from a repository (wrapper around get_file_content).

        Args:
            owner: Repository owner
            repo: Repository name
            path: Path to content
            ref: Git reference (branch, tag, commit)

        Returns:
            Content information

        Raises:
            GitHubError: If the API request fails
            RateLimitError: If rate limited
        """
        ref = ref or "HEAD"
        return await self.get_file_content(owner, repo, path, ref)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
    )
    async def get_latest_release(self, owner: str, repo: str) -> dict[str, Any]:
        """
        Get the latest release for a repository.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            Latest release information including tag_name

        Raises:
            GitHubError: If the API request fails
            RateLimitError: If rate limited
            ModuleNotFoundError: If no releases exist
        """
        cache_key = f"latest_release_{owner}_{repo}"

        # Check cache first
        cached = self.cache.get(cache_key)
        if cached:
            log_cache_operation(self.logger, "get", cache_key, hit=True)
            return cached

        log_cache_operation(self.logger, "get", cache_key, hit=False)

        start_time = time.time()

        try:
            response = await self.client.get(f"/repos/{owner}/{repo}/releases/latest")
            duration_ms = (time.time() - start_time) * 1000

            self._update_rate_limit_info(response)

            # Handle rate limiting
            if response.status_code == 429:
                raise RateLimitError(
                    "GitHub rate limit exceeded",
                    reset_time=int(self.rate_limit_reset)
                    if self.rate_limit_reset
                    else None,
                    api_name="GitHub",
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
                repo=f"{owner}/{repo}",
                tag_name=data.get("tag_name"),
            )

            # Cache the result with shorter TTL for latest release
            self.cache.set(cache_key, data, ttl=300)  # 5 minutes for latest release
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
            if e.response.status_code == 404:
                raise ModuleNotFoundError(
                    f"{owner}/{repo}",
                    details={"reason": "No releases found"},
                ) from e
            raise GitHubError(
                f"HTTP error getting latest release: {e}",
                status_code=e.response.status_code,
                response_body=e.response.text,
            ) from e

        except httpx.RequestError as e:
            duration_ms = (time.time() - start_time) * 1000
            self.logger.error("Request error getting latest release", error=str(e))
            raise GitHubError(f"Request error getting latest release: {e}") from e

    async def resolve_version(
        self, owner: str, repo: str, version: str = "latest"
    ) -> str:
        """
        Resolve version to actual git reference.

        For "latest", attempts to get the latest release tag. If no releases exist,
        falls back to "HEAD".

        Args:
            owner: Repository owner
            repo: Repository name
            version: Version to resolve (default: "latest")

        Returns:
            Resolved git reference (tag name, branch name, or "HEAD")
        """
        if version != "latest":
            return version

        try:
            release_data = await self.get_latest_release(owner, repo)
            resolved_version = release_data.get("tag_name", "HEAD")

            self.logger.info(
                "Resolved latest version to release tag",
                repo=f"{owner}/{repo}",
                resolved_version=resolved_version,
            )

            return resolved_version

        except ModuleNotFoundError:
            self.logger.warning(
                "No releases found, falling back to HEAD",
                repo=f"{owner}/{repo}",
            )
            return "HEAD"
        except Exception as e:
            self.logger.warning(
                "Failed to resolve latest version, falling back to HEAD",
                repo=f"{owner}/{repo}",
                error=str(e),
            )
            return "HEAD"
