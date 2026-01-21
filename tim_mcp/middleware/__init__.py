"""Per-IP rate limiting middleware using limits library."""

import time
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ..utils.rate_limiter import RateLimiter


class PerIPRateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP rate limiting middleware."""

    def __init__(self, app, rate_limiter: RateLimiter, bypass_paths: list[str] | None = None):
        super().__init__(app)
        self.rate_limiter = rate_limiter
        self.bypass_paths = bypass_paths or ["/health"]

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from headers."""
        if forwarded := request.headers.get("X-Forwarded-For"):
            return forwarded.split(",")[0].strip()
        if real_ip := request.headers.get("X-Real-IP"):
            return real_ip
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Apply per-IP rate limiting."""
        if request.url.path in self.bypass_paths:
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        allowed, reset_time = self.rate_limiter.check_limit(client_ip)

        if not allowed:
            stats = self.rate_limiter.get_stats(client_ip)
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too Many Requests",
                    "message": f"Rate limit exceeded. Try again after {reset_time}",
                    "reset_time": reset_time,
                },
                headers={
                    "X-RateLimit-Limit": str(stats["limit"]),
                    "X-RateLimit-Remaining": str(stats["remaining"]),
                    "X-RateLimit-Reset": str(reset_time) if reset_time else "",
                    "Retry-After": str(reset_time - int(time.time())) if reset_time else "60",
                },
            )

        response = await call_next(request)
        stats = self.rate_limiter.get_stats(client_ip)
        response.headers["X-RateLimit-Limit"] = str(stats["limit"])
        response.headers["X-RateLimit-Remaining"] = str(stats["remaining"])
        if stats["reset_time"]:
            response.headers["X-RateLimit-Reset"] = str(stats["reset_time"])

        return response
