"""
Transport configuration for TIM-MCP server.

This module defines configuration classes for different transport modes
supported by FastMCP.
"""

from dataclasses import dataclass
from typing import Literal

TransportMode = Literal["stdio", "http"]


@dataclass
class TransportConfig:
    """Base transport configuration."""

    mode: TransportMode


@dataclass
class StdioConfig(TransportConfig):
    """Configuration for STDIO transport (default)."""

    mode: TransportMode = "stdio"


@dataclass
class HttpConfig(TransportConfig):
    """Configuration for HTTP transport."""

    mode: TransportMode = "http"
    host: str = "127.0.0.1"
    port: int = 8000

    def __post_init__(self):
        """Validate HTTP configuration."""
        if not isinstance(self.port, int):
            raise ValueError("Port must be an integer")

        if not (1 <= self.port <= 65535):
            raise ValueError("Port must be between 1 and 65535")

        if not self.host:
            raise ValueError("Host cannot be empty")


def create_transport_config(
    use_http: bool = False, host: str = "127.0.0.1", port: int = 8000
) -> TransportConfig:
    """
    Create a transport configuration based on parameters.

    Args:
        use_http: Whether to use HTTP transport (False = STDIO)
        host: Host for HTTP transport (ignored if use_http=False)
        port: Port for HTTP transport (ignored if use_http=False)

    Returns:
        Appropriate transport configuration

    Raises:
        ValueError: If HTTP configuration is invalid
    """
    if use_http:
        return HttpConfig(host=host, port=port)
    else:
        return StdioConfig()
