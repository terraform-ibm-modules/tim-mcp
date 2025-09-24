"""
Terraform Registry tools for Tim MCP.

This module provides functionality for interacting with the Terraform Registry,
including searching for modules, providers, and retrieving metadata.
"""

import logging
from typing import Any

from ..clients.terraform_client import TerraformClient

logger = logging.getLogger(__name__)


class RegistryTools:
    """Tools for interacting with the Terraform Registry."""

    def __init__(self, client: TerraformClient | None = None):
        """
        Initialize the registry tools.

        Args:
            client: Terraform client instance, or None to create a new one
        """
        self.client = client or TerraformClient()

    def search_modules(
        self, query: str, namespace: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Search for modules in the Terraform Registry.

        Args:
            query: Search query
            namespace: Optional namespace to filter by

        Returns:
            List of matching modules
        """
        logger.info(f"Searching for modules with query: {query}")
        return self.client.search_modules(query, namespace)

    def get_module_versions(self, namespace: str, name: str) -> list[str]:
        """
        Get available versions for a module.

        Args:
            namespace: Module namespace
            name: Module name

        Returns:
            List of available versions
        """
        logger.info(f"Getting versions for module {namespace}/{name}")
        return self.client.get_module_versions(namespace, name)

    def get_provider_info(self, namespace: str, name: str) -> dict[str, Any]:
        """
        Get information about a provider.

        Args:
            namespace: Provider namespace
            name: Provider name

        Returns:
            Provider information
        """
        logger.info(f"Getting info for provider {namespace}/{name}")
        return self.client.get_provider_info(namespace, name)


# Made with Bob
