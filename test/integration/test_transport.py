"""
Tests for transport configuration module.
"""

import pytest

from tim_mcp.transport import HttpConfig, StdioConfig, create_transport_config


class TestStdioConfig:
    """Tests for STDIO transport configuration."""

    def test_default_values(self):
        """Test STDIO config has correct default values."""
        config = StdioConfig()
        assert config.mode == "stdio"

    def test_explicit_values(self):
        """Test STDIO config can be created explicitly."""
        config = StdioConfig(mode="stdio")
        assert config.mode == "stdio"


class TestHttpConfig:
    """Tests for HTTP transport configuration."""

    def test_default_values(self):
        """Test HTTP config has correct default values."""
        config = HttpConfig()
        assert config.mode == "http"
        assert config.host == "127.0.0.1"
        assert config.port == 8000

    def test_custom_values(self):
        """Test HTTP config with custom values."""
        config = HttpConfig(host="0.0.0.0", port=9000)
        assert config.mode == "http"
        assert config.host == "0.0.0.0"
        assert config.port == 9000

    def test_port_validation_invalid_type(self):
        """Test that non-integer port raises ValueError."""
        with pytest.raises(ValueError, match="Port must be an integer"):
            HttpConfig(port="8000")  # String instead of int

    def test_port_validation_too_low(self):
        """Test that port below 1 raises ValueError."""
        with pytest.raises(ValueError, match="Port must be between 1 and 65535"):
            HttpConfig(port=0)

    def test_port_validation_too_high(self):
        """Test that port above 65535 raises ValueError."""
        with pytest.raises(ValueError, match="Port must be between 1 and 65535"):
            HttpConfig(port=65536)

    def test_port_validation_edge_cases(self):
        """Test that edge case ports are valid."""
        # Valid edge cases
        config_low = HttpConfig(port=1)
        assert config_low.port == 1

        config_high = HttpConfig(port=65535)
        assert config_high.port == 65535

    def test_host_validation_empty(self):
        """Test that empty host raises ValueError."""
        with pytest.raises(ValueError, match="Host cannot be empty"):
            HttpConfig(host="")

    def test_host_validation_none(self):
        """Test that None host raises ValueError."""
        with pytest.raises(ValueError, match="Host cannot be empty"):
            HttpConfig(host=None)


class TestCreateTransportConfig:
    """Tests for transport configuration factory function."""

    def test_create_stdio_default(self):
        """Test creating STDIO config (default)."""
        config = create_transport_config()
        assert isinstance(config, StdioConfig)
        assert config.mode == "stdio"

    def test_create_stdio_explicit(self):
        """Test creating STDIO config explicitly."""
        config = create_transport_config(use_http=False)
        assert isinstance(config, StdioConfig)
        assert config.mode == "stdio"

    def test_create_http_default(self):
        """Test creating HTTP config with defaults."""
        config = create_transport_config(use_http=True)
        assert isinstance(config, HttpConfig)
        assert config.mode == "http"
        assert config.host == "127.0.0.1"
        assert config.port == 8000

    def test_create_http_custom(self):
        """Test creating HTTP config with custom values."""
        config = create_transport_config(use_http=True, host="0.0.0.0", port=9000)
        assert isinstance(config, HttpConfig)
        assert config.mode == "http"
        assert config.host == "0.0.0.0"
        assert config.port == 9000

    def test_create_stdio_ignores_http_params(self):
        """Test that STDIO creation ignores HTTP parameters."""
        config = create_transport_config(use_http=False, host="ignored", port=1234)
        assert isinstance(config, StdioConfig)
        assert config.mode == "stdio"
        # HTTP params should be ignored, no host/port attributes

    def test_create_http_invalid_port(self):
        """Test that invalid port raises ValueError."""
        with pytest.raises(ValueError, match="Port must be between 1 and 65535"):
            create_transport_config(use_http=True, port=0)

    def test_create_http_invalid_host(self):
        """Test that invalid host raises ValueError."""
        with pytest.raises(ValueError, match="Host cannot be empty"):
            create_transport_config(use_http=True, host="")
