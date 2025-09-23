"""
Exception classes for TIM-MCP.

This module defines custom exception classes used throughout the TIM-MCP
server for better error handling and debugging.
"""

from typing import Any


class TIMError(Exception):
    """Base exception class for TIM-MCP errors."""

    def __init__(
        self,
        message: str,
        code: str = "TIM_ERROR",
        details: dict[str, Any] | None = None,
    ):
        """
        Initialize TIM error.

        Args:
            message: Error message
            code: Error code for programmatic handling
            details: Additional error details
        """
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


class APIError(TIMError):
    """Exception for external API errors."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_body: str | None = None,
        api_name: str = "Unknown",
        **kwargs,
    ):
        """
        Initialize API error.

        Args:
            message: Error message
            status_code: HTTP status code
            response_body: API response body
            api_name: Name of the API that failed
            **kwargs: Additional details
        """
        details = {
            "api_name": api_name,
            "status_code": status_code,
            "response_body": response_body,
            **kwargs,
        }
        super().__init__(message, code="API_ERROR", details=details)
        self.status_code = status_code
        self.response_body = response_body
        self.api_name = api_name


class TerraformRegistryError(APIError):
    """Exception for Terraform Registry API errors."""

    def __init__(self, message: str, **kwargs):
        """Initialize Terraform Registry error."""
        super().__init__(message, api_name="Terraform Registry", **kwargs)


class GitHubError(APIError):
    """Exception for GitHub API errors."""

    def __init__(self, message: str, **kwargs):
        """Initialize GitHub error."""
        super().__init__(message, api_name="GitHub", **kwargs)


class ModuleNotFoundError(TIMError):
    """Exception for when a module cannot be found."""

    def __init__(self, module_id: str, **kwargs):
        """
        Initialize module not found error.

        Args:
            module_id: The module identifier that was not found
            **kwargs: Additional details
        """
        message = f"Module not found: {module_id}"
        details = {"module_id": module_id, **kwargs}
        super().__init__(message, code="MODULE_NOT_FOUND", details=details)
        self.module_id = module_id


class ValidationError(TIMError):
    """Exception for validation errors."""

    def __init__(self, message: str, field: str | None = None, **kwargs):
        """
        Initialize validation error.

        Args:
            message: Error message
            field: Field that failed validation
            **kwargs: Additional details
        """
        details = {"field": field, **kwargs}
        super().__init__(message, code="VALIDATION_ERROR", details=details)
        self.field = field


class RateLimitError(APIError):
    """Exception for API rate limit errors."""

    def __init__(
        self,
        message: str,
        reset_time: int | None = None,
        api_name: str = "Unknown",
        **kwargs,
    ):
        """
        Initialize rate limit error.

        Args:
            message: Error message
            reset_time: Unix timestamp when rate limit resets
            api_name: Name of the API that rate limited
            **kwargs: Additional details
        """
        details = {"reset_time": reset_time, **kwargs}
        super().__init__(message, status_code=429, api_name=api_name, code="RATE_LIMIT", **details)
        self.reset_time = reset_time


class ConfigurationError(TIMError):
    """Exception for configuration errors."""

    def __init__(self, message: str, setting: str | None = None, **kwargs):
        """
        Initialize configuration error.

        Args:
            message: Error message
            setting: Configuration setting that caused the error
            **kwargs: Additional details
        """
        details = {"setting": setting, **kwargs}
        super().__init__(message, code="CONFIGURATION_ERROR", details=details)
        self.setting = setting


class CircuitBreakerError(TIMError):
    """Exception for circuit breaker tripped state."""

    def __init__(self, service: str, **kwargs):
        """
        Initialize circuit breaker error.

        Args:
            service: Service name that has circuit breaker tripped
            **kwargs: Additional details
        """
        message = f"Circuit breaker open for service: {service}"
        details = {"service": service, **kwargs}
        super().__init__(message, code="CIRCUIT_BREAKER_OPEN", details=details)
        self.service = service
