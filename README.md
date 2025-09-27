# Terraform IBM Modules MCP

[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)
[![Renovate enabled](https://img.shields.io/badge/renovate-enabled-brightgreen.svg)](https://renovatebot.com/)
[![semantic-release](https://img.shields.io/badge/%20%20%F0%9F%93%A6%F0%9F%9A%80-semantic--release-e10079.svg)](https://github.com/semantic-release/semantic-release)
[![Experimental](https://img.shields.io/badge/status-experimental-orange.svg)](#)

A [Model Context Protocol (MCP) server](https://modelcontextprotocol.io/docs/getting-started/intro) that provides structured access to the [Terraform IBM Modules (TIM)](https://github.com/terraform-ibm-modules) ecosystem. TIM is a curated collection of IBM Cloud Terraform modules designed to follow best practices. See the [Overview](#overview) for further details on rational.

This server acts as a bridge, enabling AI models and other tools to intelligently discover and utilize the extensive documentation, examples, and implementation patterns bundled with the [TIM modules](https://github.com/terraform-ibm-modules). It is designed to support AI-assisted coding workflows for creating IBM Cloud infrastructure.

## Quick Start

Get started with TIM-MCP in Claude Desktop in under 2 minutes:

1. **Install uv** (if not already installed):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Add to Claude Desktop** - Copy this configuration to `~/Library/Application Support/Claude/claude_desktop_config.json`:
   ```json
   {
     "mcpServers": {
       "tim-mcp": {
         "command": "uvx",
         "args": [
           "--from",
           "git+https://github.com/terraform-ibm-modules/tim-mcp.git",
           "tim-mcp"
         ]
       }
     }
   }
   ```

   **Optional: Add GitHub Token** (recommended to avoid rate limits):
   ```json
   {
     "mcpServers": {
       "tim-mcp": {
         "command": "uvx",
         "args": [
           "--from",
           "git+https://github.com/terraform-ibm-modules/tim-mcp.git",
           "tim-mcp"
         ],
         "env": { "GITHUB_TOKEN": "your_github_token_here" }
       }
     }
   }
   ```

3. **Restart Claude Desktop** and look for the 🔨 icon to confirm MCP tools are loaded.

4. **Test it**: Ask Claude "What IBM Cloud VPC modules are available?"

## Overview

This MCP server provides tools for AI models to navigate the [Terraform IBM Modules (TIM)](https://github.com/terraform-ibm-modules) ecosystem. TIM modules are bundled with extensive documentation, working examples, and architectural patterns, but these resources are distributed across many GitHub repositories.

This server exposes a set of tools that allow an AI assistant to:
- **Discover** relevant modules from the [Terraform Registry](https://registry.terraform.io/namespaces/terraform-ibm-modules).
- **Inspect** module details, including inputs, outputs, and dependencies.
- **Explore** the contents of a module's repository, such as examples and submodules.
- **Retrieve** specific file contents, like example code or documentation.

The goal is to provide a structured and efficient way for an AI to gather the necessary context to generate accurate and high-quality Infrastructure as Code solutions for IBM Cloud.

### Key Features

- **Module Search**: Find modules in the Terraform Registry with quality-based ranking.
- **Module Details**: Get structured information about a module's interface.
- **Repository Exploration**: List the contents of a module's repository, including examples and submodules.
- **Content Retrieval**: Fetch specific files from a module's repository.
- **AI-Assisted Workflows**: The tools are designed to be used in sequence to support a typical AI-assisted coding workflow.

### Important Notes

⚠️ **Experimental Status**: This MCP server and the solutions it helps generate are experimental. Generated configurations should always be reviewed by skilled practitioners before use in any environment.

⚠️ **Human Review Required**: Even when the tools and workflows mature, human expertise will remain essential for reviewing outputs, making final adjustments, and ensuring configurations meet specific requirements.

## Development Installation

For developers who want to contribute to TIM-MCP or run it locally for development purposes:

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

> **Note:** For most users, we recommend using the Quick Start guide above rather than installing locally. The Quick Start method automatically handles dependencies and is easier to maintain.

## Transport Modes

TIM-MCP supports two transport modes for different deployment scenarios:

### STDIO Mode (Default)

STDIO is the default transport mode, perfect for MCP clients like Claude Desktop that spawn server processes on-demand.

```bash
# STDIO mode (default)
tim-mcp

# Explicit STDIO mode (same as default)
tim-mcp --log-level DEBUG
```

### HTTP Mode

HTTP mode runs the server as a stateless web service, ideal for network deployments and multiple concurrent clients. The server runs in stateless mode, which means no session IDs are required and each request is handled independently.

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
- Simplified client implementation

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

### Environment Variables

- `GITHUB_TOKEN` (optional): GitHub personal access token
  - **When to use:** Recommended for frequent usage to avoid GitHub API rate limits
  - **Not required for:** Basic functionality - the server works fine without it for light usage
  - **Permissions needed:** None (read-only access to public repositories)
  - **Create token at:** https://github.com/settings/tokens
- `TIM_ALLOWED_NAMESPACES`: Comma-separated list of allowed module namespaces (default: `terraform-ibm-modules`)
- `TIM_EXCLUDED_MODULES`: Comma-separated list of module IDs to exclude from search results

## MCP Configuration

TIM-MCP can be configured as an MCP server for use with Claude Desktop or other MCP clients. Choose the configuration method that best fits your needs:

### Option 1: Remote Configuration (Recommended for Users)

This method downloads and runs TIM-MCP directly from the GitHub repository without requiring local installation.

**Basic Configuration** (recommended):
```json
{
  "mcpServers": {
    "tim-mcp": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/terraform-ibm-modules/tim-mcp.git",
        "tim-mcp"
      ]
    }
  }
}
```

**With GitHub Token** (recommended for frequent usage to avoid rate limits):
```json
{
  "mcpServers": {
    "tim-mcp": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/terraform-ibm-modules/tim-mcp.git",
        "tim-mcp"
      ],
      "env": {
        "GITHUB_TOKEN": "your_github_token_here"
      }
    }
  }
}
```

**Pinned Version** (recommended for production - replace `vX.X.X` with desired version):
```json
{
  "mcpServers": {
    "tim-mcp": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/terraform-ibm-modules/tim-mcp.git@vX.X.X",
        "tim-mcp"
      ],
      "env": {
        "GITHUB_TOKEN": "your_github_token_here"
      }
    }
  }
}
```

> **Note:** Check the [releases page](https://github.com/terraform-ibm-modules/tim-mcp/releases) for the latest version tag. Pinning to a specific version ensures consistent behavior and prevents unexpected changes from updates.

**Requirements:**
- [uv](https://docs.astral.sh/uv/) package manager installed on your system
- GitHub token (optional but recommended to avoid rate limits)

### Option 2: Local Development Configuration

This method is ideal for development and testing, using your local clone of the repository.

#### For Claude Desktop

**Basic Configuration:**
```json
{
  "mcpServers": {
    "tim-terraform": {
      "command": "uv",
      "args": [
        "run",
        "tim-mcp"
      ],
      "cwd": "/path/to/your/tim-mcp"
    }
  }
}
```

**With GitHub Token** (recommended for heavy usage):
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

#### For Claude Code

For local development with Claude Code:

```bash
# Navigate to your tim-mcp directory first
cd /path/to/your/tim-mcp

# Add the local MCP server with GitHub token
claude mcp add tim-mcp --env GITHUB_TOKEN=your_github_token_here \
  -- uv run tim-mcp

# Or without GitHub token (may hit rate limits)
claude mcp add tim-mcp -- uv run tim-mcp

# List configured MCP servers
claude mcp list

# Remove if needed
claude mcp remove tim-mcp
```

**Important:** Run these commands from within your local tim-mcp repository directory, as Claude Code will use the current working directory when executing the MCP server.


## Verification

After configuration, restart Claude Desktop completely. You should see a hammer icon (🔨) in the bottom left of the input box, indicating that MCP tools are available.

Test the connection by asking Claude: "What IBM Cloud Terraform modules are available for VPC?"

## Troubleshooting

**Server not starting:**
- Ensure `uv` is installed and available in your PATH
- Check that Python 3.11+ is available
- Verify the repository path is correct for local configuration

**No tools appearing in Claude:**
- Restart Claude Desktop completely (quit and reopen)
- Check the Claude Desktop logs for error messages
- Verify your MCP configuration JSON syntax is valid

**Rate limiting errors:**
- Add a `GITHUB_TOKEN` environment variable with a valid GitHub personal access token
- The token needs no special permissions for public repositories

**Import errors:**
- For local development, ensure you've run `uv sync` to install dependencies
- Check that the `cwd` path points to your local tim-mcp directory

## Contributing

You can report issues and request features for this module in GitHub issues in the module repo. See [Report an issue or request a feature](https://github.com/terraform-ibm-modules/.github/blob/main/.github/SUPPORT.md).
