# TIM-MCP Development Guide

This guide is for developers who want to contribute to or modify the TIM-MCP server itself.

## Development Installation

For developers who want to contribute to TIM-MCP or run it locally:

```bash
# Clone the repository
git clone https://github.com/terraform-ibm-modules/tim-mcp.git
cd tim-mcp

# Install development dependencies
uv sync

# Run tests
uv run pytest

# Run the server locally (STDIO mode - default)
uv run tim-mcp

# Launch the MCP inspector
npx @modelcontextprotocol/inspector uv run tim-mcp
```

**Requirements:**
- Python 3.11 or higher
- [uv](https://docs.astral.sh/uv/) package manager

## Local Development Configuration

### For Claude Desktop

```json
{
  "mcpServers": {
    "tim-terraform": {
      "command": "uv",
      "args": [
        "run",
        "tim-mcp"
      ],
      "cwd": "/path/to/your/tim-mcp",
      "env": {
        "GITHUB_TOKEN": "your_github_token_here"
      }
    }
  }
}
```

**Setup steps:**
1. Clone the repository: `git clone https://github.com/terraform-ibm-modules/tim-mcp.git`
2. Navigate to the directory: `cd tim-mcp`
3. Install dependencies: `uv sync`
4. Update the `cwd` path in the configuration above to match your local repository path
5. Add the configuration to your Claude Desktop settings

### For Claude Code

```bash
# Navigate to your tim-mcp directory first
cd /path/to/your/tim-mcp

# Add the local MCP server
claude mcp add tim-mcp --env GITHUB_TOKEN=your_github_token_here -- uv run tim-mcp
```

## Transport Modes

TIM-MCP supports two transport modes for different deployment scenarios:

### STDIO Mode (Default)

STDIO is the default transport mode, perfect for MCP clients like Claude Desktop that spawn server processes on-demand.

```bash
# STDIO mode (default)
tim-mcp

# Explicit STDIO mode with debug logging
tim-mcp --log-level DEBUG
```

### HTTP Mode

HTTP mode runs the server as a stateless web service, ideal for network deployments and multiple concurrent clients.

```bash
# HTTP mode with defaults (127.0.0.1:8000)
tim-mcp --http

# HTTP mode with custom port
tim-mcp --http --port 8080

# HTTP mode with custom host and port
tim-mcp --http --host 0.0.0.0 --port 9000

# HTTP mode with debug logging
tim-mcp --http --log-level DEBUG
```

**HTTP Server URLs:**
- Server runs at: `http://host:port/`
- MCP endpoint: `http://host:port/mcp`

**Stateless Operation:**
- No session IDs required for HTTP requests
- Each request is processed independently
- Ideal for load balancing and horizontal scaling

**Production HTTPS:**
For production deployments requiring HTTPS, use nginx as a reverse proxy:

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    # SSL configuration
    ssl_certificate /path/to/your/cert.pem;
    ssl_certificate_key /path/to/your/key.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Advanced Configuration

### Environment Variables

- `GITHUB_TOKEN` (optional): GitHub personal access token
  - **When to use:** Recommended for frequent usage to avoid GitHub API rate limits
  - **Not required for:** Basic functionality - the server works fine without it for light usage
  - **Permissions needed:** None (read-only access to public repositories)
  - **Create token at:** https://github.com/settings/tokens

- `TIM_ALLOWED_NAMESPACES`: Comma-separated list of allowed module namespaces (default: `terraform-ibm-modules`)
- `TIM_EXCLUDED_MODULES`: Comma-separated list of module IDs to exclude from search results

### Debugging

For development and debugging purposes:

```bash
# Run with debug logging
tim-mcp --log-level DEBUG

# Run with trace logging (very verbose)
tim-mcp --log-level TRACE
```

## Contributing

You can report issues and request features for this module in GitHub issues in the module repo. See [Report an issue or request a feature](https://github.com/terraform-ibm-modules/.github/blob/main/.github/SUPPORT.md).
