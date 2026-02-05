"""Per-IP rate limiting middleware using limits library."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ..utils.rate_limiter import RateLimiter

# Default retry-after value when reset_time is not available (in seconds)
DEFAULT_RETRY_AFTER = 60


class PerIPRateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP rate limiting middleware."""

    def __init__(
        self, app, rate_limiter: RateLimiter, bypass_paths: list[str] | None = None
    ):
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

    async def dispatch(self, request: Request, call_next) -> Response:
        """Apply per-IP rate limiting."""
        if request.url.path in self.bypass_paths:
            return await call_next(request)

        acquired, reset_time = self.rate_limiter.try_acquire(
            self._get_client_ip(request)
        )
        if not acquired:
            return JSONResponse(
                status_code=429,
                content={"error": "Too Many Requests"},
                headers={"Retry-After": str(reset_time or DEFAULT_RETRY_AFTER)},
            )
        return await call_next(request)
