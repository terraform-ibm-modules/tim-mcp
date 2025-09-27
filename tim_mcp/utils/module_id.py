"""
Module ID parsing utilities for TIM-MCP.

This module provides utilities for parsing module IDs that may include version information.
"""

from ..exceptions import ValidationError


def parse_module_id_with_version(module_id: str) -> tuple[str, str, str, str]:
    """
    Parse a module ID that may include a version into its components.

    Args:
        module_id: Full module identifier, either:
                  - "namespace/name/provider" (without version)
                  - "namespace/name/provider/version" (with version)

    Returns:
        Tuple of (namespace, name, provider, version)
        If no version is provided, version will be "latest"

    Raises:
        ValidationError: If module_id format is invalid
    """
    if not module_id or not isinstance(module_id, str):
        raise ValidationError("module_id cannot be empty", field="module_id")

    parts = module_id.split("/")

    if len(parts) == 3:
        # Format: namespace/name/provider (no version)
        namespace, name, provider = parts
        version = "latest"
    elif len(parts) == 4:
        # Format: namespace/name/provider/version
        namespace, name, provider, version = parts
    else:
        raise ValidationError(
            f"Invalid module_id format. Expected 'namespace/name/provider' or 'namespace/name/provider/version', got '{module_id}'",
            field="module_id",
        )

    if not all([namespace.strip(), name.strip(), provider.strip()]):
        raise ValidationError("module_id components cannot be empty", field="module_id")

    if not version.strip():
        raise ValidationError("version cannot be empty", field="module_id")

    return namespace.strip(), name.strip(), provider.strip(), version.strip()


def parse_module_id(module_id: str) -> tuple[str, str, str]:
    """
    Parse a module ID into its components (without version).

    Args:
        module_id: Full module identifier, either:
                  - "namespace/name/provider" (without version)
                  - "namespace/name/provider/version" (with version)

    Returns:
        Tuple of (namespace, name, provider)

    Raises:
        ValidationError: If module_id format is invalid
    """
    namespace, name, provider, _ = parse_module_id_with_version(module_id)
    return namespace, name, provider


def get_module_base_id(module_id: str) -> str:
    """
    Get the base module ID (without version) from a full module ID.

    Args:
        module_id: Full module identifier, either:
                  - "namespace/name/provider" (without version)
                  - "namespace/name/provider/version" (with version)

    Returns:
        Base module ID in format "namespace/name/provider"

    Raises:
        ValidationError: If module_id format is invalid
    """
    namespace, name, provider, _ = parse_module_id_with_version(module_id)
    return f"{namespace}/{name}/{provider}"


def get_module_version(module_id: str) -> str:
    """
    Extract the version from a full module ID.

    Args:
        module_id: Full module identifier, either:
                  - "namespace/name/provider" (without version, returns "latest")
                  - "namespace/name/provider/version" (with version)

    Returns:
        Version string, or "latest" if no version in module_id

    Raises:
        ValidationError: If module_id format is invalid
    """
    _, _, _, version = parse_module_id_with_version(module_id)
    return version


def transform_version_for_github(version: str) -> str:
    """
    Transform version for GitHub tag lookup.
    
    TIM modules use "v" prefixed versions in GitHub tags (e.g., "v1.2.3").
    This function adds the "v" prefix if not present and not "latest".
    
    Args:
        version: Version string (e.g., "1.2.3", "v1.2.3", "latest")
        
    Returns:
        Version string with "v" prefix for GitHub lookup (e.g., "v1.2.3", "latest")
    """
    if version == "latest" or version.startswith("v"):
        return version
    return f"v{version}"