# Stage 1: Builder
FROM registry.access.redhat.com/ubi8/python-312:latest AS builder

# Run as root for build stage to avoid permission issues
USER root
WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

# Copy dependency files and README (required by pyproject.toml)
COPY pyproject.toml README.md ./

# Copy source code (needed for editable install)
COPY tim_mcp ./tim_mcp
COPY static ./static

# Ensure all files are owned by default user (1001 in UBI)
RUN chown -R 1001:0 /app && chmod -R g+w /app

# Install dependencies
# Set version for hatch-vcs since .git is not available in Docker
ARG VERSION=1.8.10
ENV SETUPTOOLS_SCM_PRETEND_VERSION=${VERSION}

# Switch to default user for dependency installation
USER 1001
RUN uv sync --no-dev

# Stage 2: Runtime
FROM registry.access.redhat.com/ubi8/python-312:latest

# Run as root to set up files
USER root
WORKDIR /app

# Copy uv binary
COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv

# Copy installed dependencies
COPY --from=builder /app/.venv /app/.venv

# Copy application code and static files
COPY tim_mcp ./tim_mcp
COPY static ./static
COPY pyproject.toml ./

# Set ownership to default UBI user (1001) and group 0 (root group)
RUN chown -R 1001:0 /app && chmod -R g+w /app

# Switch to default non-root user
USER 1001

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
