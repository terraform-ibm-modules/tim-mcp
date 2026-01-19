# Stage 1: Builder
FROM python:3.14.2-slim AS builder
WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

# Copy dependency files and README (required by pyproject.toml)
COPY pyproject.toml uv.lock README.md ./

# Copy source code (needed for editable install)
COPY tim_mcp ./tim_mcp
COPY static ./static

# Install dependencies
# Set version for hatch-vcs since .git is not available in Docker
ARG VERSION=1.8.10
ENV SETUPTOOLS_SCM_PRETEND_VERSION=${VERSION}
RUN uv sync --frozen --no-dev

# Stage 2: Runtime
FROM python:3.14.2-slim
WORKDIR /app

# Copy uv binary
COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv

# Copy installed dependencies
COPY --from=builder /app/.venv /app/.venv

# Copy application code and static files
COPY tim_mcp ./tim_mcp
COPY static ./static
COPY pyproject.toml ./

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash --uid 1000 timuser && \
    chown -R timuser:timuser /app

USER timuser

# Environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PORT=8080

EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health').read()"

# Run in HTTP mode on all interfaces
CMD ["python", "-m", "tim_mcp.main", "--http", "--host", "0.0.0.0", "--port", "8080"]
