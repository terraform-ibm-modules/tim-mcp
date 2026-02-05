"""
Tests for parameter sanitization in the MCP server.

This module tests the input sanitization functionality that handles
cases where LLMs might pass JSON strings instead of proper arrays.
"""

import pytest

from tim_mcp.server import _sanitize_list_parameter


class TestParameterSanitization:
    """Test cases for parameter sanitization."""

    def test_sanitize_valid_list(self):
        """Test sanitization of lists with mixed patterns."""
        input_list = [".*\\.tf$", ".*\\.md$", "main.tf"]
        result = _sanitize_list_parameter(input_list, "test_param")
        # Patterns are preserved as-is for glob matching
        expected = [".*\\.tf$", ".*\\.md$", "main.tf"]
        assert result == expected

    def test_sanitize_none(self):
        """Test sanitization handles None correctly."""
        result = _sanitize_list_parameter(None, "test_param")
        assert result is None

    def test_sanitize_empty_list(self):
        """Test sanitization preserves empty lists."""
        input_list = []
        result = _sanitize_list_parameter(input_list, "test_param")
        assert result == []
        # Note: result may not be the same object due to pattern processing

    def test_sanitize_json_string(self):
        """Test sanitization converts JSON strings to lists."""
        # Test with proper regex patterns
        json_str = '[".*\\\\.tf$", ".*\\\\.md$"]'
        result = _sanitize_list_parameter(json_str, "test_param")
        expected = [".*\\.tf$", ".*\\.md$"]
        assert result == expected

        # Test with single item (glob pattern preserved)
        json_str = '["main.tf"]'
        result = _sanitize_list_parameter(json_str, "test_param")
        assert result == ["main.tf"]

        # Test with empty array
        json_str = "[]"
        result = _sanitize_list_parameter(json_str, "test_param")
        assert result == []

    def test_sanitize_single_string(self):
        """Test sanitization converts single strings to lists."""
        # Glob patterns are preserved
        result = _sanitize_list_parameter("*.tf", "test_param")
        assert result == ["*.tf"]

        result = _sanitize_list_parameter("main.tf", "test_param")
        assert result == ["main.tf"]

        # Regex patterns are preserved
        result = _sanitize_list_parameter(".*\\.tf$", "test_param")
        assert result == [".*\\.tf$"]

    def test_sanitize_invalid_json_string(self):
        """Test sanitization handles invalid JSON strings as single strings."""
        # Malformed JSON
        result = _sanitize_list_parameter('["invalid json"', "test_param")
        assert result == ['["invalid json"']

        # Not actually JSON
        result = _sanitize_list_parameter("not-json", "test_param")
        assert result == ["not-json"]

    def test_sanitize_json_with_non_strings(self):
        """Test sanitization handles JSON arrays with non-string items."""
        # JSON with numbers - should be treated as single string
        json_str = "[1, 2, 3]"
        result = _sanitize_list_parameter(json_str, "test_param")
        assert result == [json_str]

        # JSON with mixed types - should be treated as single string
        json_str = '["string", 123, null]'
        result = _sanitize_list_parameter(json_str, "test_param")
        assert result == [json_str]

    def test_sanitize_invalid_types(self):
        """Test sanitization rejects invalid types."""
        with pytest.raises(ValueError, match="must be a list of strings"):
            _sanitize_list_parameter(123, "test_param")

        with pytest.raises(ValueError, match="must be a list of strings"):
            _sanitize_list_parameter({"key": "value"}, "test_param")

        with pytest.raises(ValueError, match="must be a list of strings"):
            _sanitize_list_parameter(True, "test_param")

    def test_sanitize_list_with_non_strings(self):
        """Test sanitization rejects lists with non-string items."""
        with pytest.raises(ValueError, match="must be a list of strings"):
            _sanitize_list_parameter(["string", 123], "test_param")

        with pytest.raises(ValueError, match="must be a list of strings"):
            _sanitize_list_parameter([123, 456], "test_param")

    def test_sanitize_whitespace_handling(self):
        """Test sanitization handles whitespace correctly."""
        # JSON string with extra whitespace
        json_str = '  [".*\\\\.tf$", ".*\\\\.md$"]  '
        result = _sanitize_list_parameter(json_str, "test_param")
        assert result == [".*\\.tf$", ".*\\.md$"]

        # Regular string with whitespace preserved as-is
        result = _sanitize_list_parameter("  *.tf  ", "test_param")
        # Pattern is preserved as-is
        assert len(result) == 1
        assert result[0] == "  *.tf  "

    def test_sanitize_complex_patterns(self):
        """Test sanitization with complex regex patterns."""
        patterns = [
            r".*\.tf$",
            r"examples/.*\.tf$",
            r"^(?!.*test).*\.tf$",
            r"modules/[^/]+/.*\.tf$",
        ]

        # Test as proper list
        result = _sanitize_list_parameter(patterns, "test_param")
        assert result == patterns

        # Test as JSON string
        import json

        json_str = json.dumps(patterns)
        result = _sanitize_list_parameter(json_str, "test_param")
        assert result == patterns

    def test_glob_pattern_conversion(self):
        """Test glob patterns are preserved as-is."""
        # Test basic glob patterns
        glob_patterns = ["*.tf", "*.md", "main.tf"]
        result = _sanitize_list_parameter(glob_patterns, "test_param")

        # Patterns are preserved as-is for glob matching
        expected = ["*.tf", "*.md", "main.tf"]
        assert result == expected

    def test_mixed_glob_and_regex_patterns(self):
        """Test handling of mixed glob and regex patterns."""
        mixed_patterns = ["*.tf", ".*\\.py$", "README.md", "^test.*\\.js$"]
        result = _sanitize_list_parameter(mixed_patterns, "test_param")

        # All patterns are preserved as-is
        expected = ["*.tf", ".*\\.py$", "README.md", "^test.*\\.js$"]
        assert result == expected

    def test_complex_glob_patterns(self):
        """Test complex glob patterns with wildcards."""
        glob_patterns = ["examples/*.tf", "modules/*/main.tf", "*.{tf,py}"]
        result = _sanitize_list_parameter(glob_patterns, "test_param")

        # Patterns are preserved as-is
        assert result == glob_patterns

    def test_single_glob_string_conversion(self):
        """Test single glob pattern string preserved."""
        result = _sanitize_list_parameter("*.tf", "test_param")
        assert result == ["*.tf"]

        result = _sanitize_list_parameter("main.py", "test_param")
        assert result == ["main.py"]

    def test_json_string_with_glob_patterns(self):
        """Test JSON string containing glob patterns."""
        json_str = '["*.tf", "*.md"]'
        result = _sanitize_list_parameter(json_str, "test_param")
        expected = ["*.tf", "*.md"]
        assert result == expected
