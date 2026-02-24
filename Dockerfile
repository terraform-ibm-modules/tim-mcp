FROM registry.access.redhat.com/ubi9/python-312:latest AS builder
USER root
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv
COPY pyproject.toml README.md ./
COPY tim_mcp ./tim_mcp
COPY static ./static
RUN chown -R 1001:0 /app && chmod -R g+w /app

# hatch-vcs needs a version since .git is absent
ARG VERSION=0.0.0
ENV SETUPTOOLS_SCM_PRETEND_VERSION=${VERSION}

USER 1001
RUN UV_CACHE_DIR=/app/.uv-cache uv sync --no-dev && rm -rf /app/.uv-cache

FROM registry.access.redhat.com/ubi9/python-312:latest
USER root
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY tim_mcp ./tim_mcp
COPY static ./static
COPY pyproject.toml ./
RUN chown -R 1001:0 /app && chmod -R g+w /app
USER 1001

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health').read()"
CMD ["python", "-m", "tim_mcp.main", "--http", "--host", "0.0.0.0"]
