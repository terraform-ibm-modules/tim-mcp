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
        """Test sanitization preserves valid lists."""
        input_list = [".*\\.tf$", ".*\\.md$", "main.tf"]
        result = _sanitize_list_parameter(input_list, "test_param")
        assert result == input_list
        assert result is input_list  # Should return the same object

    def test_sanitize_none(self):
        """Test sanitization handles None correctly."""
        result = _sanitize_list_parameter(None, "test_param")
        assert result is None

    def test_sanitize_empty_list(self):
        """Test sanitization preserves empty lists."""
        input_list = []
        result = _sanitize_list_parameter(input_list, "test_param")
        assert result == []
        assert result is input_list  # Should return the same object

    def test_sanitize_json_string(self):
        """Test sanitization converts JSON strings to lists."""
        # Test with proper regex patterns
        json_str = '[".*\\\\.tf$", ".*\\\\.md$"]'
        result = _sanitize_list_parameter(json_str, "test_param")
        expected = [".*\\.tf$", ".*\\.md$"]
        assert result == expected

        # Test with single item
        json_str = '["main.tf"]'
        result = _sanitize_list_parameter(json_str, "test_param")
        assert result == ["main.tf"]

        # Test with empty array
        json_str = "[]"
        result = _sanitize_list_parameter(json_str, "test_param")
        assert result == []

    def test_sanitize_single_string(self):
        """Test sanitization converts single strings to lists."""
        result = _sanitize_list_parameter("*.tf", "test_param")
        assert result == ["*.tf"]

        result = _sanitize_list_parameter("main.tf", "test_param")
        assert result == ["main.tf"]

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

        # Regular string with whitespace
        result = _sanitize_list_parameter("  *.tf  ", "test_param")
        assert result == ["  *.tf  "]  # Should preserve whitespace in content

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
