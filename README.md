# Terraform IBM Modules MCP

[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)
[![Renovate enabled](https://img.shields.io/badge/renovate-enabled-brightgreen.svg)](https://renovatebot.com/)
[![semantic-release](https://img.shields.io/badge/%20%20%F0%9F%93%A6%F0%9F%9A%80-semantic--release-e10079.svg)](https://github.com/semantic-release/semantic-release)
[![Experimental](https://img.shields.io/badge/status-experimental-orange.svg)](#)

A [Model Context Protocol (MCP) server](https://modelcontextprotocol.io/docs/getting-started/intro) that provides structured access to the [Terraform IBM Modules (TIM)](https://github.com/terraform-ibm-modules) ecosystem. TIM is a curated collection of IBM Cloud Terraform modules designed to follow best practices.

## Table of Contents
- [Overview](#overview)
- [About TIM-MCP](#about-tim-mcp)
- [Install TIM-MCP](#install-tim-mcp)
- [Using TIM-MCP](#using-tim-mcp)
- [Troubleshooting](#troubleshooting)
- [Configuration](#configuration)
- [Additional Resources](#additional-resources)
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

## About TIM-MCP

TIM-MCP connects AI assistants to curated Terraform IBM Modules so generated infrastructure is more accurate, aligned to IBM Cloud best practices, and grounded in real module interfaces.

To get started quickly, read [about TIM-MCP](https://cloud.ibm.com/docs/ibm-cloud-provider-for-terraform?topic=ibm-cloud-provider-for-terraform-about-tim-mcp).

## Install TIM-MCP

For installation, version pinning, and usage workflows, follow the instructions provided in [TIM-MCP tutorial](https://cloud.ibm.com/docs/ibm-cloud-provider-for-terraform?topic=ibm-cloud-provider-for-terraform-using-tim-mcp).

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

## Troubleshooting

If you face any issue, use the [troubleshooting guide](https://cloud.ibm.com/docs/ibm-cloud-provider-for-terraform?topic=ibm-cloud-provider-for-terraform-troubleshoot-tim-mcp-error) to diagnose and resolve common errors.

## Configuration

#### Basic Configuration

For most users running TIM-MCP locally, you only need these environment variables:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GITHUB_TOKEN` | Recommended | None | GitHub PAT for API rate limits (5000 req/hr vs 60 req/hr) |
| `TIM_LOG_LEVEL` | No | INFO | Logging level (DEBUG, INFO, WARNING, ERROR) |

#### Advanced Configuration (Production/Hosting)

These settings are for advanced users deploying TIM-MCP in production or HTTP mode:

| Variable | Default | Description |
|----------|---------|-------------|
| `TIM_CACHE_FRESH_TTL` | 3600 | Fresh cache TTL in seconds |
| `TIM_CACHE_EVICT_TTL` | 86400 | Eviction TTL in seconds (stale entries persist until this) |
| `TIM_CACHE_MAXSIZE` | 1000 | Maximum cache entries (LRU eviction when exceeded) |
| `TIM_GLOBAL_RATE_LIMIT` | None | Global rate limit: max requests per minute across all clients (unset = unlimited) |
| `TIM_PER_IP_RATE_LIMIT` | None | Per-IP rate limit: max requests per minute per client IP in HTTP mode (unset = unlimited) |
| `TIM_RATE_LIMIT_WINDOW` | 60 | Rate limit time window in seconds |
| `TIM_REQUEST_TIMEOUT` | 30 | External API timeout in seconds |
| `TIM_ALLOWED_NAMESPACES` | terraform-ibm-modules | Allowed module namespaces (comma-separated) |

## Additional Resources

- **TIM-MCP Repository:** https://github.com/terraform-ibm-modules/tim-mcp
- **Model Context Protocol Docs:** https://modelcontextprotocol.io
- **GitHub API Rate Limit Docs:** https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api
- **Terraform Registry (IBM Modules):** https://registry.terraform.io/namespaces/terraform-ibm-modules

## Contributing

If you're interested in contributing to TIM-MCP or modifying the server itself, please see the [Development Guide](DEVELOPMENT.md) for detailed instructions on development setup, transport modes, and advanced configuration options.

You can report issues and request features for this module in GitHub issues in the module repo. See [Report an issue or request a feature](https://github.com/terraform-ibm-modules/.github/blob/main/.github/SUPPORT.md).
