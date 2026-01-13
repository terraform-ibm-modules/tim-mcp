"""
Middleware for TIM-MCP HTTP server.

This module provides middleware components for the HTTP server,
including per-IP rate limiting.
"""

from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ..logging import get_logger
from ..utils.rate_limiter import RateLimiter

logger = get_logger(__name__)


class PerIPRateLimitMiddleware(BaseHTTPMiddleware):
    """
    Per-IP rate limiting middleware for HTTP server.

    Applies rate limiting based on client IP address extracted from headers.
    Returns 429 Too Many Requests with rate limit headers when exceeded.
    """

    def __init__(
        self,
        app,
        rate_limiter: RateLimiter,
        bypass_paths: list[str] | None = None,
    ):
        """
        Initialize the per-IP rate limit middleware.

        Args:
            app: ASGI application
            rate_limiter: RateLimiter instance for per-IP limiting
            bypass_paths: List of paths to bypass rate limiting (e.g., ["/health"])
        """
        super().__init__(app)
        self.rate_limiter = rate_limiter
        self.bypass_paths = bypass_paths or ["/health"]

    def _get_client_ip(self, request: Request) -> str:
        """
        Extract client IP address from request headers.

        Checks headers in order:
        1. X-Forwarded-For (first IP in comma-separated list)
        2. X-Real-IP
        3. client.host (direct connection)

        Args:
            request: Starlette request object

        Returns:
            Client IP address as string
        """
        # Check X-Forwarded-For header (proxy/load balancer)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP in the chain (original client)
            client_ip = forwarded_for.split(",")[0].strip()
            logger.debug(
                "Client IP from X-Forwarded-For",
                forwarded_for=forwarded_for,
                client_ip=client_ip,
            )
            return client_ip

        # Check X-Real-IP header (alternative proxy header)
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            logger.debug("Client IP from X-Real-IP", client_ip=real_ip)
            return real_ip

        # Fall back to direct connection host
        client_host = request.client.host if request.client else "unknown"
        logger.debug("Client IP from direct connection", client_ip=client_host)
        return client_host

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request with per-IP rate limiting.

        Args:
            request: Starlette request object
            call_next: Next middleware/endpoint in chain

        Returns:
            Response from next middleware or 429 if rate limited
        """
        # Bypass rate limiting for specific paths
        if request.url.path in self.bypass_paths:
            return await call_next(request)

        # Extract client IP
        client_ip = self._get_client_ip(request)

        # Check rate limit
        allowed, reset_time = self.rate_limiter.check_limit(client_ip)

        if not allowed:
            # Rate limit exceeded
            logger.warning(
                "Per-IP rate limit exceeded",
                client_ip=client_ip,
                reset_time=reset_time,
                path=request.url.path,
            )

            # Get current stats for response headers
            stats = self.rate_limiter.get_stats(client_ip)

            # Return 429 with rate limit headers
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too Many Requests",
                    "message": f"Rate limit exceeded. Please try again after {reset_time}",
                    "reset_time": reset_time,
                },
                headers={
                    "X-RateLimit-Limit": str(stats["limit"]),
                    "X-RateLimit-Remaining": str(stats["remaining"]),
                    "X-RateLimit-Reset": str(reset_time) if reset_time else "",
                    "Retry-After": str(reset_time - int(__import__("time").time()))
                    if reset_time
                    else "60",
                },
            )

        # Record request
        self.rate_limiter.record_request(client_ip)

        # Continue to next middleware/endpoint
        response = await call_next(request)

        # Add rate limit headers to successful responses
        stats = self.rate_limiter.get_stats(client_ip)
        response.headers["X-RateLimit-Limit"] = str(stats["limit"])
        response.headers["X-RateLimit-Remaining"] = str(stats["remaining"])
        if stats["reset_time"]:
            response.headers["X-RateLimit-Reset"] = str(stats["reset_time"])

        return response
