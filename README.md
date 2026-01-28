# Terraform IBM Modules MCP

[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)
[![Renovate enabled](https://img.shields.io/badge/renovate-enabled-brightgreen.svg)](https://renovatebot.com/)
[![semantic-release](https://img.shields.io/badge/%20%20%F0%9F%93%A6%F0%9F%9A%80-semantic--release-e10079.svg)](https://github.com/semantic-release/semantic-release)
[![Experimental](https://img.shields.io/badge/status-experimental-orange.svg)](#)

A [Model Context Protocol (MCP) server](https://modelcontextprotocol.io/docs/getting-started/intro) that provides structured access to the [Terraform IBM Modules (TIM)](https://github.com/terraform-ibm-modules) ecosystem. TIM is a curated collection of IBM Cloud Terraform modules designed to follow best practices.

## Table of Contents
- [Overview](#overview)
- [Why TIM-MCP?](#why-tim-mcp)
- [Prerequisites](#prerequisites)
- [Installation Instructions](#installation-instructions)
  - [Claude Desktop](#claude-desktop)
  - [VS Code](#vs-code)
  - [Cursor](#cursor)
  - [IBM Bob](#ibm-bob)
  - [Claude Code](#claude-code)
- [Version Pinning](#version-pinning)
- [Verification](#verification)
- [Troubleshooting](#troubleshooting)
- [Using TIM-MCP](#using-tim-mcp)
- [Additional Resources](#additional-resources)
- [For Developers](#for-developers)
- [Contributing](#contributing)

## Overview

The TIM-MCP server acts as a bridge between AI models and the Terraform IBM Modules ecosystem, enabling intelligent discovery and utilization of IBM Cloud infrastructure resources.

### Key Features

- **Module Search**: Find relevant modules in the Terraform Registry with quality-based ranking
- **Module Details**: Get structured information about inputs, outputs, and dependencies
- **Repository Exploration**: Navigate examples, submodules, and implementation patterns
- **Content Retrieval**: Access documentation, example code, and other repository files
- **White Paper Resource**: Access the IBM Cloud Terraform Best Practices white paper
- **AI-Assisted Workflows**: Tools designed to support infrastructure code generation

### Important Notes

⚠️ **Experimental Status**: This MCP server and the solutions it helps generate are experimental. Generated configurations should always be reviewed by skilled practitioners before use in any environment.

⚠️ **Human Review Required**: Even when the tools and workflows mature, human expertise will remain essential for reviewing outputs, making final adjustments, and ensuring configurations meet specific requirements.

## Why TIM-MCP?

TIM-MCP guides foundation models (FMs) to produce better IBM Cloud infrastructure solutions by:

### Steering models toward best practices
Without TIM-MCP, foundation models might generate generic or outdated Terraform code. TIM-MCP steers models toward IBM-validated patterns and current best practices by providing direct access to curated modules, preventing common anti-patterns and ensuring alignment with IBM Cloud architecture recommendations.

### Providing contextual guardrails
TIM-MCP acts as a guardrail system, helping models navigate the complex IBM Cloud ecosystem. It provides structured access to module interfaces, dependencies, and implementation patterns, reducing the likelihood of hallucinated parameters or incompatible resource combinations.

### Enhancing precision with real-time module data
Foundation models may have limited or outdated knowledge of IBM Cloud Terraform modules. TIM-MCP provides real-time access to module details, ensuring AI assistants generate code with accurate input variables, correct resource configurations, and proper module versioning.

### Unlocking distributed knowledge
By connecting models to documentation and examples spread across many repositories, TIM-MCP helps foundation models leverage the collective expertise embedded in the TIM ecosystem, resulting in more accurate and production-ready infrastructure code.

## Prerequisites

Before configuring TIM-MCP, ensure you have the following installed:

1. **uv Package Manager** (required for running the MCP server)

   **macOS/Linux:**
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

   **Windows:**
   ```powershell
   winget install --id=astral-sh.uv -e
   ```

   Verify installation:
   ```bash
   uv --version
   ```

2. **GitHub Personal Access Token** (optional but recommended)

   A GitHub token helps avoid API rate limits when accessing TIM repositories:
   - Without token: 60 requests/hour
   - With token: 5,000 requests/hour

   To create a token:
   - Go to: **GitHub Settings → Developer settings → Personal access tokens → Fine-grained tokens**
   - Create a token with:
     - **Repository access:** "Public repositories only"
     - **Permissions:** No private access scopes needed
     - **Expiration:** Set to 90 days or longer

## Installation Instructions

### Claude Desktop

Claude Desktop is a standalone application that supports MCP servers through a JSON configuration file.

1. **Install uv** (if not already installed) - see Prerequisites section

2. **Add TIM-MCP Configuration**:
   - **macOS:** Edit `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Windows:** Edit `%APPDATA%\Claude\claude_desktop_config.json`

   **Basic Configuration:**
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

   **With GitHub Token** (recommended to avoid rate limits):
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

3. **Restart Claude Desktop** and look for the 🔨 icon to confirm MCP tools are loaded

4. **Test it**: Ask Claude "What IBM Cloud VPC modules are available?"

### VS Code

Visual Studio Code supports MCP servers through extension and configuration files.

1. **Install the MCP extension** for VS Code if not already installed

2. **Configure TIM-MCP** using one of these methods:
   - Create/edit `.vscode/mcp.json` in your project directory
   - Use the Command Palette (Ctrl+Shift+P or Cmd+Shift+P) and select "MCP: Add Server"

3. **Add the configuration** using the same JSON format as shown in the [Claude Desktop](#claude-desktop) section

### Cursor

Cursor IDE supports MCP servers through configuration files.

1. **Create/edit** one of these files:
   - `.cursor/mcp.json` in your project directory
   - `~/.cursor/mcp.json` for global configuration

2. **Add the configuration** using the same JSON format as shown in the [Claude Desktop](#claude-desktop) section

### IBM Bob

[IBM Bob](https://www.ibm.com/products/bob) supports MCP servers through configuration files.

#### Configuring MCP Servers in Bob

MCP server configurations can be managed at two levels:

- **Project-level Configuration**: Create the file `.bob/mcp.json` within your project directory, and then **add the configuration** using the JSON format shown in the [Claude Desktop](#claude-desktop) section
- **Global Configuration**: Stored in the `mcp_settings.json` file, accessible via VS Code settings. These settings apply across all your workspaces unless overridden by a project-level configuration.
  1. Click the icon in the top navigation of the Bob pane.
  2. Scroll to the bottom of the MCP settings view.
  3. Click **Edit Global MCP**: Opens the global `mcp_settings.json` file.
  4. Add the configuration using the same JSON format as shown in the [Claude Desktop](#claude-desktop) section


### Claude Code

Claude Code supports configuration via CLI or config file. The configuration format is similar to the [Claude Desktop](#claude-desktop) section.

**CLI Method:**
```bash
# Navigate to your project directory first
cd /path/to/your/project

# Add the MCP server with GitHub token
claude mcp add tim-mcp --env GITHUB_TOKEN=your_github_token_here \
  -- uvx --from git+https://github.com/terraform-ibm-modules/tim-mcp.git tim-mcp

# Or without GitHub token (may hit rate limits)
claude mcp add tim-mcp -- uvx --from git+https://github.com/terraform-ibm-modules/tim-mcp.git tim-mcp

# List configured MCP servers
claude mcp list

# Remove if needed
claude mcp remove tim-mcp
```


## Configuration

### Environment Variables

#### Basic Configuration

For most users running TIM-MCP locally, you only need:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GITHUB_TOKEN` | Recommended | None | GitHub PAT for API rate limits (5000 req/hr vs 60 req/hr) |
| `TIM_LOG_LEVEL` | No | INFO | Logging level (DEBUG, INFO, WARNING, ERROR) |

<details>
<summary><strong>Advanced Configuration (Production/Hosting)</strong></summary>

These settings are for advanced users deploying TIM-MCP in production or HTTP mode:

| Variable | Default | Description |
|----------|---------|-------------|
| `TIM_CACHE_FRESH_TTL` | 3600 | Fresh cache TTL in seconds |
| `TIM_CACHE_EVICT_TTL` | 86400 | Eviction TTL in seconds (stale entries persist until this) |
| `TIM_CACHE_MAXSIZE` | 1000 | Maximum cache entries (LRU eviction when exceeded) |
| `TIM_GLOBAL_RATE_LIMIT` | 30 | Global rate limit: max requests per minute across all clients |
| `TIM_PER_IP_RATE_LIMIT` | 10 | Per-IP rate limit: max requests per minute per client IP (HTTP mode only) |
| `TIM_RATE_LIMIT_WINDOW` | 60 | Rate limit time window in seconds |
| `TIM_REQUEST_TIMEOUT` | 30 | External API timeout in seconds |
| `TIM_ALLOWED_NAMESPACES` | terraform-ibm-modules | Allowed module namespaces (comma-separated) |

</details>

## Version Pinning

For production use, pin to a specific version to ensure consistent behavior (using the same format as in the [Claude Desktop](#claude-desktop) section):

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
      "env": { "GITHUB_TOKEN": "your_github_token_here" }
    }
  }
}
```

> **Note:** Check the [releases page](https://github.com/terraform-ibm-modules/tim-mcp/releases) for the latest version tag.

## Verification

After configuration:

1. **Restart** your IDE or Claude Desktop completely
2. **Check** for the hammer icon (🔨) in the input box, indicating MCP tools are available
3. **Test** by asking: "What IBM Cloud Terraform modules are available for VPC?"

## Troubleshooting

### Common Issues and Solutions

**Server not starting:**
- Ensure `uv` is installed and available in your PATH
- Verify your MCP configuration JSON syntax is valid

**No tools appearing:**
- Restart your IDE or Claude Desktop completely
- Check logs for error messages

**Rate limiting errors:**
- Add a `GITHUB_TOKEN` environment variable with a valid GitHub personal access token
- The token needs only public repository access permissions

**Token Authentication Fails:**
1. Verify token is valid and not expired
2. Check token has public repository access
3. Ensure token is in quotes in JSON
4. Test token manually:
```bash
curl -H "Authorization: token YOUR_TOKEN" https://api.github.com/user
```

## Using TIM-MCP

Once configured, your AI assistant can help you build IBM Cloud infrastructure from simple to complex deployments. Ask for help with scenarios like:

### Getting Started with IBM Cloud
- "I am new to IBM Cloud. Help me create a simple and cheap OpenShift cluster and access the console"
- "I want to create a simple basic virtual server on IBM Cloud and SSH to it"

### Building Enterprise Infrastructure
- "Design a VPC + OpenShift: Create a complete container platform with networking, including multi-zone VPC, subnets, OpenShift/ROKS cluster, and load balancers"
- "Design a Secure Landing Zone: Implement enterprise-grade security with network isolation, encryption key management, private endpoints, and security groups"
- "Design a Multi-Zone HA Database: Design resilient database infrastructure across 3+ availability zones with automated failover, backup strategies, and disaster recovery"

### Quick Solutions
- "Design a Quick POC Setup: Rapidly deploy a minimal viable environment with compute instances, basic networking, and essential services for testing"
- "Design a FS-Validated Architecture: Deploy compliant infrastructure meeting Financial Services requirements with HPCS encryption, audit logging, and regulatory controls"
- "Design a Hub-Spoke Network: Create an enterprise network architecture with centralized connectivity, network segmentation, and secure VPC interconnection"

## Additional Resources

- **TIM-MCP Repository:** https://github.com/terraform-ibm-modules/tim-mcp
- **Model Context Protocol Docs:** https://modelcontextprotocol.io
- **GitHub API Rate Limit Docs:** https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api
- **Terraform Registry (IBM Modules):** https://registry.terraform.io/namespaces/terraform-ibm-modules

## For Developers

If you're interested in contributing to TIM-MCP or modifying the server itself, please see the [Development Guide](DEVELOPMENT.md) for detailed instructions on development setup, transport modes, and advanced configuration options.

## Contributing

You can report issues and request features for this module in GitHub issues in the module repo. See [Report an issue or request a feature](https://github.com/terraform-ibm-modules/.github/blob/main/.github/SUPPORT.md).
