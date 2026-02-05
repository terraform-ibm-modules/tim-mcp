"""Unit tests for PerIPRateLimitMiddleware."""

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from tim_mcp.middleware import PerIPRateLimitMiddleware
from tim_mcp.utils.rate_limiter import RateLimiter


async def hello_endpoint(request):
    """Simple test endpoint."""
    return JSONResponse({"message": "hello"})


async def health_endpoint(request):
    """Health check endpoint."""
    return JSONResponse({"status": "ok"})


def create_test_app(rate_limiter: RateLimiter, bypass_paths: list[str] | None = None):
    """Create a test Starlette app with rate limiting middleware."""
    app = Starlette(
        routes=[
            Route("/", hello_endpoint),
            Route("/api/data", hello_endpoint),
            Route("/health", health_endpoint),
        ]
    )
    app.add_middleware(
        PerIPRateLimitMiddleware,
        rate_limiter=rate_limiter,
        bypass_paths=bypass_paths or ["/health"],
    )
    return app


class TestPerIPRateLimitMiddleware:
    """Test suite for PerIPRateLimitMiddleware."""

    def test_allows_requests_under_limit(self):
        """Test that requests are allowed when under rate limit."""
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        app = create_test_app(limiter)
        client = TestClient(app)

        # Make 5 requests (at limit)
        for i in range(5):
            response = client.get("/")
            assert response.status_code == 200
            assert response.json() == {"message": "hello"}

    def test_blocks_requests_over_limit(self):
        """Test that requests are blocked when over rate limit."""
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        app = create_test_app(limiter)
        client = TestClient(app)

        # First 2 requests should succeed
        for i in range(2):
            response = client.get("/")
            assert response.status_code == 200

        # Third request should be rate limited
        response = client.get("/")
        assert response.status_code == 429
        assert response.json()["error"] == "Too Many Requests"

    def test_returns_retry_after_on_429(self):
        """Test that Retry-After header is included in 429 responses."""
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        app = create_test_app(limiter)
        client = TestClient(app)

        # Use up the limit
        client.get("/")

        # Next request should be rate limited
        response = client.get("/")
        assert response.status_code == 429
        assert "Retry-After" in response.headers

    def test_bypass_paths_not_rate_limited(self):
        """Test that bypass paths are not rate limited."""
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        app = create_test_app(limiter, bypass_paths=["/health"])
        client = TestClient(app)

        # Use up the limit on regular endpoint
        response = client.get("/")
        assert response.status_code == 200

        # Health endpoint should still work (bypassed)
        for i in range(5):
            response = client.get("/health")
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}

    def test_extracts_ip_from_x_forwarded_for(self):
        """Test that client IP is extracted from X-Forwarded-For header."""
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        app = create_test_app(limiter)
        client = TestClient(app)

        # Request with X-Forwarded-For header
        response = client.get("/", headers={"X-Forwarded-For": "192.168.1.100, 10.0.0.1"})
        assert response.status_code == 200

        # Same IP should be rate limited
        response = client.get("/", headers={"X-Forwarded-For": "192.168.1.100"})
        assert response.status_code == 429

        # Different IP should be allowed
        response = client.get("/", headers={"X-Forwarded-For": "192.168.1.101"})
        assert response.status_code == 200

    def test_extracts_ip_from_x_real_ip(self):
        """Test that client IP is extracted from X-Real-IP header."""
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        app = create_test_app(limiter)
        client = TestClient(app)

        # Request with X-Real-IP header
        response = client.get("/", headers={"X-Real-IP": "10.20.30.40"})
        assert response.status_code == 200

        # Same IP should be rate limited
        response = client.get("/", headers={"X-Real-IP": "10.20.30.40"})
        assert response.status_code == 429

    def test_x_forwarded_for_takes_precedence(self):
        """Test that X-Forwarded-For takes precedence over X-Real-IP."""
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        app = create_test_app(limiter)
        client = TestClient(app)

        # Request with both headers - X-Forwarded-For should be used
        response = client.get("/", headers={
            "X-Forwarded-For": "1.1.1.1",
            "X-Real-IP": "2.2.2.2"
        })
        assert response.status_code == 200

        # Request with same X-Forwarded-For should be blocked
        response = client.get("/", headers={
            "X-Forwarded-For": "1.1.1.1",
            "X-Real-IP": "3.3.3.3"
        })
        assert response.status_code == 429

    def test_per_ip_isolation(self):
        """Test that different IPs have independent rate limits."""
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        app = create_test_app(limiter)
        client = TestClient(app)

        # IP 1 makes 2 requests
        for i in range(2):
            response = client.get("/", headers={"X-Forwarded-For": "10.0.0.1"})
            assert response.status_code == 200

        # IP 1 is now rate limited
        response = client.get("/", headers={"X-Forwarded-For": "10.0.0.1"})
        assert response.status_code == 429

        # IP 2 should still have its full quota
        for i in range(2):
            response = client.get("/", headers={"X-Forwarded-For": "10.0.0.2"})
            assert response.status_code == 200

    def test_multiple_paths_rate_limited(self):
        """Test that rate limiting applies across different paths for same IP."""
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        app = create_test_app(limiter)
        client = TestClient(app)

        # Make requests to different paths
        response = client.get("/")
        assert response.status_code == 200

        response = client.get("/api/data")
        assert response.status_code == 200

        # Third request to any path should be blocked
        response = client.get("/")
        assert response.status_code == 429

    def test_custom_bypass_paths(self):
        """Test that custom bypass paths work correctly."""
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        app = create_test_app(limiter, bypass_paths=["/health", "/api/data"])
        client = TestClient(app)

        # Use up limit on non-bypass path
        response = client.get("/")
        assert response.status_code == 200

        # Regular path is now blocked
        response = client.get("/")
        assert response.status_code == 429

        # Bypass paths still work
        response = client.get("/health")
        assert response.status_code == 200

        response = client.get("/api/data")
        assert response.status_code == 200
