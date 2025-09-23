"""
Structured logging configuration for TIM-MCP.

This module sets up structured logging using structlog for better
observability and debugging.
"""

import logging
import sys
from typing import Any

import structlog
from structlog.stdlib import LoggerFactory

from .config import Config


def configure_logging(config: Config) -> None:
    """
    Configure structured logging for the application.

    Args:
        config: Configuration instance with logging settings
    """
    # Set logging level
    log_level = getattr(logging, config.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        stream=sys.stderr,
    )

    if config.structured_logging:
        # Configure structlog for structured output
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.processors.JSONRenderer(),
            ],
            context_class=dict,
            logger_factory=LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
    else:
        # Configure structlog for simple text output
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.dev.ConsoleRenderer(),
            ],
            context_class=dict,
            logger_factory=LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )


def get_logger(name: str, **kwargs: Any) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger instance.

    Args:
        name: Logger name (usually __name__)
        **kwargs: Additional context to bind to the logger

    Returns:
        Configured structured logger
    """
    logger = structlog.get_logger(name)
    if kwargs:
        logger = logger.bind(**kwargs)
    return logger


def log_api_request(
    logger: structlog.stdlib.BoundLogger,
    method: str,
    url: str,
    status_code: int,
    duration_ms: float,
    **kwargs: Any,
) -> None:
    """
    Log API request with structured data.

    Args:
        logger: Structured logger instance
        method: HTTP method
        url: Request URL
        status_code: Response status code
        duration_ms: Request duration in milliseconds
        **kwargs: Additional context
    """
    logger.info(
        "API request completed",
        method=method,
        url=url,
        status_code=status_code,
        duration_ms=duration_ms,
        **kwargs,
    )


def log_cache_operation(
    logger: structlog.stdlib.BoundLogger,
    operation: str,
    key: str,
    hit: bool = False,
    **kwargs: Any,
) -> None:
    """
    Log cache operation with structured data.

    Args:
        logger: Structured logger instance
        operation: Cache operation (get, set, invalidate, etc.)
        key: Cache key
        hit: Whether operation was a cache hit
        **kwargs: Additional context
    """
    logger.debug(
        "Cache operation",
        operation=operation,
        key=key,
        hit=hit,
        **kwargs,
    )


def log_tool_execution(
    logger: structlog.stdlib.BoundLogger,
    tool_name: str,
    parameters: dict[str, Any],
    duration_ms: float,
    success: bool = True,
    **kwargs: Any,
) -> None:
    """
    Log MCP tool execution with structured data.

    Args:
        logger: Structured logger instance
        tool_name: Name of the executed tool
        parameters: Tool parameters
        duration_ms: Execution duration in milliseconds
        success: Whether execution was successful
        **kwargs: Additional context
    """
    logger.info(
        "Tool execution completed",
        tool_name=tool_name,
        parameters=parameters,
        duration_ms=duration_ms,
        success=success,
        **kwargs,
    )
