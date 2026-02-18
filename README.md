# Terraform IBM Modules MCP

[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)
[![Renovate enabled](https://img.shields.io/badge/renovate-enabled-brightgreen.svg)](https://renovatebot.com/)
[![semantic-release](https://img.shields.io/badge/%20%20%F0%9F%93%A6%F0%9F%9A%80-semantic--release-e10079.svg)](https://github.com/semantic-release/semantic-release)
[![Experimental](https://img.shields.io/badge/status-experimental-orange.svg)](#)

A [Model Context Protocol (MCP) server](https://modelcontextprotocol.io/docs/getting-started/intro) that provides structured access to the [Terraform IBM Modules (TIM)](https://github.com/terraform-ibm-modules) ecosystem. TIM is a curated collection of IBM Cloud Terraform modules designed to follow best practices.

## Table of Contents
- [Terraform IBM Modules MCP](#terraform-ibm-modules-mcp)
  - [Table of Contents](#table-of-contents)
  - [Overview](#overview)
    - [Key Features](#key-features)
    - [Important Notes](#important-notes)
  - [Why TIM-MCP?](#why-tim-mcp)
  - [Installing TIM-MCP](#installing-tim-mcp)
  - [Troubleshooting](#troubleshooting)
  - [Using TIM-MCP](#using-tim-mcp)
    - [Getting Started with IBM Cloud](#getting-started-with-ibm-cloud)
    - [Building Enterprise Infrastructure](#building-enterprise-infrastructure)
    - [Quick Solutions](#quick-solutions)
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

For detailed information about TIM-MCP, its benefits, and how it works with AI assistants, see the [IBM Cloud documentation](https://cloud.ibm.com/docs/ibm-cloud-provider-for-terraform?topic=ibm-cloud-provider-for-terraform-about-tim-mcp).

## Installing TIM-MCP

For detailed installation instructions, prerequisites, configuration options, and troubleshooting guidance, see the [IBM Cloud documentation](https://cloud.ibm.com/docs/ibm-cloud-provider-for-terraform?topic=ibm-cloud-provider-for-terraform-using-tim-mcp).

## Troubleshooting

If you encounter errors while installing or using TIM-MCP, see the [troubleshooting guide](https://cloud.ibm.com/docs/ibm-cloud-provider-for-terraform?topic=ibm-cloud-provider-for-terraform-troubleshoot-tim-mcp-error) for solutions to common issues.

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
