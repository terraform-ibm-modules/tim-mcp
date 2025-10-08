"""
Version filtering utilities for TIM-MCP.

This module provides utilities to filter out pre-release versions from
Terraform module and provider version lists, ensuring only stable versions
are displayed to users.
"""

import re


def is_stable_version(version: str) -> bool:
    """
    Check if a version string represents a stable release.

    A stable version contains only numbers and dots, with no pre-release
    suffixes like -beta, -rc, -alpha, -dev, etc.

    Args:
        version: Version string to check (e.g., "1.2.3" or "1.2.3-beta0")

    Returns:
        True if the version is stable, False if it's a pre-release

    Examples:
        >>> is_stable_version("1.2.3")
        True
        >>> is_stable_version("1.2.3-beta0")
        False
        >>> is_stable_version("2.0.0-rc1")
        False
        >>> is_stable_version("1.0.0-alpha")
        False
    """
    if not version:
        return False

    # A stable version should only contain digits and dots
    # Any hyphen indicates a pre-release suffix
    # Pattern: one or more groups of digits separated by dots, nothing else
    stable_pattern = r"^\d+(\.\d+)*$"

    return bool(re.match(stable_pattern, version))


def filter_stable_versions(versions: list[str]) -> list[str]:
    """
    Filter a list of versions to include only stable releases.

    This function removes all pre-release versions (those with suffixes like
    -beta, -rc, -alpha, etc.) from the input list, preserving the original order.

    Args:
        versions: List of version strings to filter

    Returns:
        List containing only stable versions, in the same order as input

    Examples:
        >>> filter_stable_versions(["1.2.3", "1.2.3-beta0", "1.2.2"])
        ['1.2.3', '1.2.2']
        >>> filter_stable_versions(["2.0.0-rc1", "1.9.0", "1.8.0"])
        ['1.9.0', '1.8.0']
        >>> filter_stable_versions([])
        []
    """
    if not versions:
        return []

    return [v for v in versions if is_stable_version(v)]


def get_latest_stable_version(versions: list[str]) -> str | None:
    """
    Get the latest stable version from a list of versions.

    This function filters out pre-release versions and assumes the input list
    is chronologically ordered (oldest to newest, as returned by the
    Terraform Registry API).

    Args:
        versions: List of version strings, ordered chronologically (oldest first)

    Returns:
        The last (newest) stable version found, or None if no stable versions exist

    Examples:
        >>> get_latest_stable_version(["1.2.1", "1.2.2", "1.2.3-beta0"])
        '1.2.2'
        >>> get_latest_stable_version(["1.8.0", "1.9.0-rc1", "2.0.0"])
        '2.0.0'
        >>> get_latest_stable_version(["1.0.0-beta1", "1.0.0-alpha"])
        None
    """
    stable_versions = filter_stable_versions(versions)
    return stable_versions[-1] if stable_versions else None
