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
       "tim-terraform": {
         "command": "uv",
         "args": ["run", "--from", "git+https://github.com/terraform-ibm-modules/tim-mcp.git", "tim-mcp"],
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

# Run the server locally
uv run tim-mcp
```

### Environment Variables

- `GITHUB_TOKEN`: GitHub API token for accessing private repositories and avoiding rate limits
- `TIM_ALLOWED_NAMESPACES`: Comma-separated list of allowed module namespaces (default: `terraform-ibm-modules`)
- `TIM_EXCLUDED_MODULES`: Comma-separated list of module IDs to exclude from search results

## MCP Configuration

TIM-MCP can be configured as an MCP server for use with Claude Desktop or other MCP clients. Choose the configuration method that best fits your needs:

### Option 1: Remote Configuration (Recommended for Users)

This method downloads and runs TIM-MCP directly from the GitHub repository without requiring local installation.

Add this configuration to your Claude Desktop MCP settings (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "tim-terraform": {
      "command": "uv",
      "args": [
        "run",
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

**Requirements:**
- [uv](https://docs.astral.sh/uv/) package manager installed on your system
- GitHub token (optional but recommended to avoid rate limits)

### Option 2: Local Development Configuration

This method is ideal for development and testing, using your local clone of the repository.

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


## Verification

After configuration, restart Claude Desktop completely. You should see a hammer icon (🔨) in the bottom left of the input box, indicating that MCP tools are available.

Test the connection by asking Claude: "What IBM Cloud Terraform modules are available for VPC?"

## Available MCP Tools

Once configured, TIM-MCP provides these tools to Claude:

1. **`search_modules`** - Search Terraform Registry for IBM Cloud modules
2. **`get_module_details`** - Retrieve detailed module metadata and documentation
3. **`list_content`** - Discover available files and structure in module repositories
4. **`get_content`** - Fetch source code, examples, and documentation from GitHub

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
