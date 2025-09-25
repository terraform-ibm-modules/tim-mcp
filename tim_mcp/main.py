#!/usr/bin/env python3
"""
Tim MCP - Main entry point for the MCP server.

This module initializes and runs the TIM-MCP server with support for
multiple transport modes (STDIO and HTTP).
"""

import logging
import sys

import click

from .transport import create_transport_config

logger = logging.getLogger(__name__)


@click.command()
@click.option(
    "--http",
    is_flag=True,
    help="Use HTTP transport instead of STDIO (default: STDIO)",
)
@click.option(
    "--host",
    default="127.0.0.1",
    help="Host to bind HTTP server to (default: 127.0.0.1, requires --http)",
)
@click.option(
    "--port",
    type=click.IntRange(1, 65535),
    default=8000,
    help="Port for HTTP server (default: 8000, requires --http)",
)
@click.option(
    "--log-level",
    type=click.Choice(
        ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], case_sensitive=False
    ),
    default="INFO",
    help="Set logging level (default: INFO)",
)
def cli(http: bool, host: str, port: int, log_level: str) -> None:
    """
    TIM-MCP: Terraform IBM Modules MCP Server

    \b
    Transport Modes:
      STDIO (default): Communicates via standard input/output
      HTTP: Runs as web server accessible via network

    \b
    Examples:
      tim-mcp                           # STDIO mode (default)
      tim-mcp --http                    # HTTP mode (127.0.0.1:8000)
      tim-mcp --http --port 8080        # HTTP mode on port 8080
      tim-mcp --http --host 0.0.0.0     # HTTP mode on all interfaces

    For production HTTPS, use nginx as a reverse proxy.
    """
    try:
        # Validate arguments
        if not http and (host != "127.0.0.1" or port != 8000):
            if host != "127.0.0.1":
                raise click.BadParameter("--host can only be used with --http")
            if port != 8000:
                raise click.BadParameter("--port can only be used with --http")

        # Set up logging
        logging.basicConfig(
            level=getattr(logging, log_level.upper()),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

        # Create transport configuration
        transport_config = create_transport_config(
            use_http=http,
            host=host,
            port=port,
        )

        logger.info(
            "Starting TIM-MCP server", extra={"transport": transport_config.mode}
        )

        # Import and run the server
        from .server import main as server_main

        server_main(transport_config)

    except click.ClickException:
        # Let Click handle its own exceptions
        raise
    except KeyboardInterrupt:
        logger.info("Server interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"Error starting TIM-MCP server: {e}")
        sys.exit(1)


def main(args: list[str] | None = None) -> int:
    """
    Main entry point for testing and programmatic usage.

    Args:
        args: Command line arguments

    Returns:
        Exit code
    """
    try:
        if args is None:
            cli()
        else:
            cli(args=args, standalone_mode=False)
        return 0
    except SystemExit as e:
        return e.code if e.code is not None else 0
    except Exception:
        return 1


if __name__ == "__main__":
    sys.exit(main())

# Made with Bob
