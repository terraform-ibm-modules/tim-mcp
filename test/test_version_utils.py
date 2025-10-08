"""
Tests for version filtering utilities.

These tests verify that pre-release versions are correctly identified and filtered
from version lists, ensuring only stable versions are shown to users.
"""

from tim_mcp.utils.version import (
    filter_stable_versions,
    get_latest_stable_version,
    is_stable_version,
)


class TestIsStableVersion:
    """Test stable version detection."""

    def test_stable_semantic_version(self):
        """Test that standard semantic versions are recognized as stable."""
        assert is_stable_version("1.2.3") is True
        assert is_stable_version("0.1.0") is True
        assert is_stable_version("10.20.30") is True
        assert is_stable_version("1.0.0") is True

    def test_stable_major_minor_version(self):
        """Test that major.minor versions are recognized as stable."""
        assert is_stable_version("1.2") is True
        assert is_stable_version("0.1") is True
        assert is_stable_version("10.0") is True

    def test_stable_major_only_version(self):
        """Test that major-only versions are recognized as stable."""
        assert is_stable_version("1") is True
        assert is_stable_version("2") is True
        assert is_stable_version("10") is True

    def test_beta_version(self):
        """Test that beta versions are not recognized as stable."""
        assert is_stable_version("1.2.3-beta0") is False
        assert is_stable_version("1.2.3-beta1") is False
        assert is_stable_version("1.0.0-beta") is False

    def test_rc_version(self):
        """Test that release candidate versions are not recognized as stable."""
        assert is_stable_version("2.0.0-rc1") is False
        assert is_stable_version("1.5.0-rc2") is False
        assert is_stable_version("3.0.0-rc") is False

    def test_alpha_version(self):
        """Test that alpha versions are not recognized as stable."""
        assert is_stable_version("1.0.0-alpha") is False
        assert is_stable_version("1.0.0-alpha1") is False
        assert is_stable_version("2.0.0-alpha.1") is False

    def test_dev_version(self):
        """Test that dev versions are not recognized as stable."""
        assert is_stable_version("1.0.0-dev") is False
        assert is_stable_version("1.2.3-dev1") is False

    def test_snapshot_version(self):
        """Test that snapshot versions are not recognized as stable."""
        assert is_stable_version("1.0.0-snapshot") is False
        assert is_stable_version("1.2.3-SNAPSHOT") is False

    def test_other_prerelease_suffixes(self):
        """Test that other pre-release suffixes are not recognized as stable."""
        assert is_stable_version("1.0.0-pre") is False
        assert is_stable_version("1.0.0-preview") is False
        assert is_stable_version("1.0.0-nightly") is False
        assert is_stable_version("1.0.0-test") is False

    def test_empty_string(self):
        """Test that empty string is not a stable version."""
        assert is_stable_version("") is False

    def test_none_value(self):
        """Test that None is not a stable version."""
        assert is_stable_version(None) is False

    def test_invalid_version_formats(self):
        """Test that invalid version formats are not recognized as stable."""
        assert is_stable_version("v1.2.3") is False  # 'v' prefix
        assert is_stable_version("1.2.3.4") is True  # Four parts is valid
        assert is_stable_version("abc") is False  # Non-numeric
        assert is_stable_version("1.2.x") is False  # Contains non-numeric


class TestFilterStableVersions:
    """Test version list filtering."""

    def test_filter_mixed_versions(self):
        """Test filtering a list with both stable and pre-release versions."""
        versions = ["1.2.3", "1.2.3-beta0", "1.2.2", "1.2.1-rc1", "1.2.0"]
        expected = ["1.2.3", "1.2.2", "1.2.0"]
        assert filter_stable_versions(versions) == expected

    def test_filter_all_stable(self):
        """Test filtering a list with only stable versions."""
        versions = ["3.0.0", "2.9.0", "2.8.0"]
        expected = ["3.0.0", "2.9.0", "2.8.0"]
        assert filter_stable_versions(versions) == expected

    def test_filter_all_prerelease(self):
        """Test filtering a list with only pre-release versions."""
        versions = ["2.0.0-rc1", "1.9.0-beta2", "1.8.0-alpha"]
        expected = []
        assert filter_stable_versions(versions) == expected

    def test_filter_empty_list(self):
        """Test filtering an empty list."""
        assert filter_stable_versions([]) == []

    def test_filter_preserves_order(self):
        """Test that filtering preserves the original order."""
        versions = ["5.0.0", "4.0.0-beta", "3.0.0", "2.0.0-rc1", "1.0.0"]
        expected = ["5.0.0", "3.0.0", "1.0.0"]
        assert filter_stable_versions(versions) == expected

    def test_filter_complex_versions(self):
        """Test filtering with complex version patterns."""
        versions = [
            "6.14.1",
            "6.14.0",
            "6.13.0-beta0",
            "6.12.0",
            "6.11.0-rc1",
            "6.10.0",
        ]
        expected = ["6.14.1", "6.14.0", "6.12.0", "6.10.0"]
        assert filter_stable_versions(versions) == expected

    def test_filter_real_world_example(self):
        """Test filtering with a real-world version list from Terraform Registry."""
        versions = [
            "1.2.3",
            "1.2.3-beta0",
            "1.2.2",
            "1.2.1",
            "1.2.0",
            "1.1.0",
            "1.1.0-rc1",
            "1.0.0",
        ]
        expected = ["1.2.3", "1.2.2", "1.2.1", "1.2.0", "1.1.0", "1.0.0"]
        assert filter_stable_versions(versions) == expected


class TestGetLatestStableVersion:
    """Test getting the latest stable version from a list (chronologically ordered, oldest first)."""

    def test_get_latest_with_stable_last(self):
        """Test getting latest version when the last version is stable."""
        versions = ["1.8.0", "1.9.0", "2.0.0"]
        assert get_latest_stable_version(versions) == "2.0.0"

    def test_get_latest_with_prerelease_last(self):
        """Test getting latest stable version when the last version is pre-release."""
        versions = ["1.8.0", "1.9.0", "2.0.0-beta0"]
        assert get_latest_stable_version(versions) == "1.9.0"

    def test_get_latest_with_multiple_prereleases(self):
        """Test getting latest stable version with multiple pre-release versions."""
        versions = ["2.7.0", "2.8.0", "2.9.0-beta", "3.0.0-rc1"]
        assert get_latest_stable_version(versions) == "2.8.0"

    def test_get_latest_with_all_prereleases(self):
        """Test getting latest version when all versions are pre-release."""
        versions = ["1.8.0-rc1", "1.9.0-alpha", "2.0.0-beta"]
        assert get_latest_stable_version(versions) is None

    def test_get_latest_with_empty_list(self):
        """Test getting latest version from an empty list."""
        assert get_latest_stable_version([]) is None

    def test_get_latest_with_single_stable(self):
        """Test getting latest version with a single stable version."""
        versions = ["1.0.0"]
        assert get_latest_stable_version(versions) == "1.0.0"

    def test_get_latest_with_single_prerelease(self):
        """Test getting latest version with a single pre-release version."""
        versions = ["1.0.0-beta"]
        assert get_latest_stable_version(versions) is None

    def test_get_latest_real_world_example(self):
        """Test with a real-world version list from Terraform Registry (chronological order)."""
        versions = [
            "6.12.0",
            "6.12.0-rc1",
            "6.13.0",
            "6.14.0",
            "6.14.1-beta0",
            "6.14.1-beta1",
        ]
        assert get_latest_stable_version(versions) == "6.14.0"
