# Terraform IBM Modules MCP

[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)
[![Renovate enabled](https://img.shields.io/badge/renovate-enabled-brightgreen.svg)](https://renovatebot.com/)
[![semantic-release](https://img.shields.io/badge/%20%20%F0%9F%93%A6%F0%9F%9A%80-semantic--release-e10079.svg)](https://github.com/semantic-release/semantic-release)

A Model Context Protocol (MCP) server that provides comprehensive Terraform module context for IBM Cloud architectures. This MCP server enhances the TIM Designer backend by bridging the gap between module discovery and implementation, enabling more accurate and context-aware Terraform code generation.

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

TIM-MCP combines data from the HashiCorp Terraform Registry with actual implementation details from GitHub repositories to provide rich context about IBM Cloud Terraform modules. While existing tools can search for modules and retrieve basic metadata, they lack access to real implementation code, working examples, and detailed integration patterns that are essential for generating production-ready Terraform configurations.

## Installation

TIM-MCP requires Python 3.11 or higher and uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
# Install from PyPI (when published)
uv tool install tim-mcp

# Install from source
git clone https://github.com/terraform-ibm-modules/tim-mcp.git
cd tim-mcp
uv sync
```

## Development Setup

To set up the development environment:

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
```

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

HTTP mode runs the server as a web service, ideal for network deployments and multiple concurrent clients.

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

## Available MCP Tools

Once configured, TIM-MCP provides these tools to Claude for comprehensive Terraform module discovery and implementation:

### 1. `search_modules`
**Search Terraform Registry for IBM Cloud modules with intelligent result optimization.**

**Purpose:** Find relevant modules based on search terms, with results optimized by download count for better quality.

**Inputs:**
- `query` (string, required): Specific search term (e.g., "vpc", "kubernetes", "security")
- `limit` (integer, optional): Maximum results to return (default: 10, range: 1-100)

**Output:** JSON formatted search results including:
- Module identifiers and basic metadata
- Download counts and verification status
- Descriptions and source repository URLs
- Publication dates and version information

**Usage Examples:**
- Quick reference: `limit=3` for "I need a VPC module"
- Exploring options: `limit=5-15` (default=5) for comparing alternatives
- Comprehensive research: `limit=20+` for thorough analysis

### 2. `get_module_details`
**Retrieve structured module metadata from Terraform Registry - lightweight module interface overview.**

**Purpose:** Get comprehensive module interface information including inputs, outputs, and dependencies without fetching source code.

**Inputs:**
- `module_id` (string, required): Full module identifier (e.g., "terraform-ibm-modules/vpc/ibm")
- `version` (string, optional): Specific version or "latest" (default: "latest")

**Output:** Markdown formatted module details including:
- Module description and documentation
- Required and optional input variables with types, descriptions, and defaults
- Available outputs with types and descriptions
- Provider requirements and version constraints
- Module dependencies and available versions

**When to Use:** First step after finding a module to understand its interface - often sufficient to answer user questions without fetching implementation files.

### 3. `list_content`
**Discover available paths in a module repository with README summaries.**

**Purpose:** Explore repository structure to understand available examples, submodules, and solutions before fetching specific content.

**Inputs:**
- `module_id` (string, required): Full module identifier (e.g., "terraform-ibm-modules/vpc/ibm")
- `version` (string, optional): Git tag/branch to scan (default: "latest")

**Output:** Markdown formatted content listing organized by category:
- **Root Module:** Main terraform files, inputs/outputs definitions
- **Examples:** Deployable examples showing module usage (ideal starting point)
- **Submodules:** Reusable components within the module
- **Solutions:** Complete architecture patterns for complex scenarios

**Usage Tips:** Use before `get_content` to select the most relevant path for your needs.

### 4. `get_content`
**Retrieve source code, examples, and documentation from GitHub repositories with targeted content filtering.**

**Purpose:** Fetch actual implementation files, examples, and documentation with precise filtering to avoid large responses.

**Inputs:**
- `module_id` (string, required): Full module identifier (e.g., "terraform-ibm-modules/vpc/ibm")
- `path` (string, optional): Specific path - "" (root), "examples/basic", "modules/vpc", etc.
- `include_files` (list[string], optional): Glob patterns for files to include
- `exclude_files` (list[string], optional): Glob patterns for files to exclude
- `version` (string, optional): Git tag/branch to fetch from (default: "latest")

**Output:** Markdown formatted content with file contents, organized by:
- File paths and content with appropriate syntax highlighting
- File sizes for reference
- README files are included if they match the patterns (like any other file)

**Common Glob Patterns:**
- Input variables only: `include_files=["variables.tf"]`
- Basic example: `path="examples/basic", include_files=["*.tf"]`
- Complete module: `include_files=["*.tf"]`
- Documentation: `include_files=["*.md"]`
- README only: `include_files=["README.md"]`
- Everything: `include_files=["*"]` (or omit entirely)

## Tool Workflow

The tools are designed to work together in an efficient workflow:

1. **`search_modules`** → Find relevant modules
2. **`get_module_details`** → Understand module interface (often sufficient)
3. **`list_content`** → Explore repository structure if needed
4. **`get_content`** → Fetch specific implementation details

This progressive approach minimizes API calls and provides context-aware information at each step.

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
