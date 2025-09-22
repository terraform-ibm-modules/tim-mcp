# Terraform IBM Modules (TIM) MCP Server

A MCP server designed to help leverage Terraform IBM Modules (TIM) to create comprehensive infrastructure solutions on IBM Cloud.

## Overview

TIM-MCP is a specialized FastMCP server that enables searching, retrieving, and utilizing Terraform IBM Modules to generate complete infrastructure configurations for IBM Cloud.

For detailed information about the server's functionality and usage, please refer to the [LLM Instructions](static/llm_instructions.md).

## Installation

### Prerequisites

- Python 3.12
- PDM (Python Dependency Manager)

### Setup

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd tim-mcp
   ```

2. Install dependencies using PDM:
   ```bash
   pdm install
   ```

## Usage

### Running in Debug Mode

```bash
fastmcp dev server.py
```

### Editor Configuration

Add the following configuration to your editor settings to support MCP:

```json
{
  "terraform-ibm-modules mcp server": {
    "command": "uv",
    "args": [
      "run",
      "--with",
      "fastmcp",
      "fastmcp",
      "run",
      "/path/to/tim-mcp/server.py"
    ]
  }
}
```

Replace `/path/to/tim-mcp` with the actual path to your project directory.
