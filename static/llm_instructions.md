# Terraform IBM Modules (TIM) MCP Server Instructions

## Overview

This MCP server is designed to help you leverage Terraform IBM Modules (TIM) to create comprehensive infrastructure solutions on IBM Cloud. As an LLM consuming this MCP server, you should follow these instructions to effectively generate terraform-based compositions of modules.

## About Terraform IBM Modules (TIM)

- TIM is a comprehensive suite of curated terraform modules for IBM Cloud
- Each module comes with comprehensive documentation and examples of usage
- Modules are designed to be composable, allowing you to build complex infrastructure solutions
- All modules are maintained by IBM and follow best practices for IBM Cloud infrastructure
- Examples of usage can be used to understand how to stitch modules together

## Purpose of this MCP Server

The main purpose of this MCP server is to help generate terraform-based compositions of modules. It provides tools to:

1. Search for relevant Terraform IBM Modules
2. Get detailed information about modules, including inputs, outputs, and examples
3. Access example code to understand how to use and combine modules
4. Generate complete, working Terraform configurations

## General Flow

When generating Terraform code, follow this general flow:

1. Use `search_terraform_modules` to find relevant modules based on the user query
2. Use `get_terraform_module` with the module_id obtained from search results to get more details, such as the list of examples, inputs, and outputs
3. Use `get_terraform_module_file` to get specific files from a module, particularly the main.tf file of examples, to understand how to use the module in practice
4. Repeat steps 1-3 until you have all the information needed for a full solution
5. Generate complete Terraform code that combines the necessary modules
6. Validate the generated code with `terraform init` and `terraform validate`

## Best Practices

### Use Modules Over Direct Provider Resources

- Always prefer terraform-ibm-modules over directly using the IBM Cloud Terraform provider
- Only use the IBM Cloud Terraform provider resources and data sources when there is no appropriate module available
- Gain insights from example code to understand when to use the Terraform provider versus modules

### Code Generation Guidelines

- Always generate complete working Terraform logic
- Include all necessary provider configurations, variables, and outputs
- Follow the structure and patterns shown in the module examples
- Ensure proper module versioning to maintain stability
- Include appropriate comments to explain the purpose and configuration of resources
- Always run `terraform init` and `terraform validate` on the generated logic to ensure it's valid

## Available Tools

### search_terraform_modules

```
search_terraform_modules(query: str, limit: Optional[int] = 2)
```

This tool searches for Terraform modules in the terraform-ibm-modules namespace based on a query string. Use it to find modules relevant to the user's requirements.

**Example:**
```
search_terraform_modules("vpc", 5)
```

### get_terraform_module

```
get_terraform_module(module_id: str)
```

This tool retrieves detailed information about a specific Terraform module, including its description, readme, submodules, and examples.

**Example:**
```
get_terraform_module("terraform-ibm-modules/vpc/ibm/1.0.0")
```

### get_terraform_module_file

```
get_terraform_module_file(module_id: str, path: str, file_name: str = "main.tf")
```

This tool fetches any file from a Terraform module repository. It's particularly useful for retrieving example files to understand how to use a module.

**Example:**
```
get_terraform_module_file("terraform-ibm-modules/vpc/ibm", "examples/basic", "main.tf")
```

## Example Workflow

1. User asks to create a VPC with subnets and security groups in IBM Cloud
2. Search for relevant modules: `search_terraform_modules("vpc")`
3. Get details about the VPC module: `get_terraform_module("terraform-ibm-modules/vpc/ibm")`
4. Examine an example: `get_terraform_module_file("terraform-ibm-modules/vpc/ibm", "examples/complete", "main.tf")`
5. Search for security group module: `search_terraform_modules("security group")`
6. Get details and examples for the security group module
7. Generate complete Terraform code that combines these modules
8. Validate the generated code

Remember to always generate complete, working Terraform configurations and validate them with `terraform init` and `terraform validate`.