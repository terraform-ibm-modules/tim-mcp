# Terraform IBM Modules (TIM) MCP Server Instructions

## Overview

This MCP server is designed to help you leverage Terraform IBM Modules (TIM) to create comprehensive infrastructure solutions on IBM Cloud. As an LLM consuming this MCP server, you should follow these instructions to effectively generate terraform-based compositions of modules.

## About Terraform IBM Modules (TIM)

- TIM is a comprehensive suite of curated terraform modules for IBM Cloud
- Each module comes with comprehensive documentation and examples of usage
- Modules are designed to be composable, allowing you to build complex infrastructure solutions
- All modules are maintained by IBM and follow best practices for IBM Cloud infrastructure
- Examples of usage can be used to understand how to stitch modules together
- Higher download counts indicate better maintained modules

## Purpose of this MCP Server

The main purpose of this MCP server is to help generate terraform-based compositions of modules. It provides tools and resources to:

1. Browse the module index for a high-level overview of available modules
2. Search for specific Terraform IBM Modules when needed
3. Discover available examples and repository structure
4. Get detailed information about modules, including inputs, outputs, and examples
5. Access example code and specific files to understand how to use and combine modules
6. Generate complete, working Terraform configurations

## Understanding Modules vs Submodules

**Do not confuse module IDs with submodule paths.**

### Modules
A **module** is a Terraform module published to the Terraform Registry at the repository root.

- **Module ID**: `namespace/name/provider/version` (e.g., `terraform-ibm-modules/cbr/ibm/1.33.6`)
- **Use with**: `search_modules`, `get_module_details`, Terraform registry source
- **Terraform usage**:
  ```terraform
  module "cbr" {
    source  = "terraform-ibm-modules/cbr/ibm"
    version = "1.33.6"
  }
  ```

### Submodules
A **submodule** is a nested module within a repository's `modules/` directory.

- **Path**: `modules/submodule-name` (e.g., `modules/cbr-rule-module`)
- **Discovery**: Use `list_content(module_id)` to find available submodule paths
- **Access**: Use `get_content(module_id, path="modules/submodule-name")` to retrieve content
- **Terraform usage**:
  ```terraform
  module "cbr_rule" {
    source = "git::https://github.com/terraform-ibm-modules/terraform-ibm-cbr.git//modules/cbr-rule-module?ref=v1.33.6"
  }
  ```

### Key Rules

1. **Never use submodule paths as module IDs** - `modules/cbr-rule-module` is NOT a module ID
2. **Module tools require module IDs** - Use full registry format: `terraform-ibm-modules/cbr/ibm/1.33.6`
3. **Submodule content requires both** - Module ID + path: `get_content(module_id="...", path="modules/...")`
4. **Submodules inherit parent version** - No separate versioning for submodules

## Architectural Best Practices

**ALWAYS prefer terraform-ibm-modules over direct provider resources**

Modules provide:
- Security hardening
- Standardized configurations
- Tested patterns
- Best practices implementation

Use direct provider resources only when no suitable module exists.

## Module Hallucination Prevention

**NEVER hallucinate or assume module names based on patterns.**

This is the most important rule when using this MCP server. You MUST:

1. **ALWAYS verify modules exist** before using them in generated code
2. **Use `search_modules`** or check the module index FIRST
3. **Use exact module IDs** from search results - never modify or infer them
4. **NEVER assume** a module exists because a similar one does
5. **NEVER infer** module names from naming patterns

This applies to ALL modules across ALL categories (compute, networking, observability, security, databases, etc.).

**Example of incorrect behavior:**
```terraform
# WRONG - This module doesn't exist!
module "log_analysis" {
  source  = "terraform-ibm-modules/log-analysis/ibm"  # Hallucinated!
  version = "1.9.2"
  ...
}
```

**Correct approach:**
```terraform
# CORRECT - Use the actual module that exists
module "observability_instances" {
  source  = "terraform-ibm-modules/observability-instances/ibm"  # Verified to exist
  version = "3.5.3"
  ...
}
```

**Real-world example of this mistake:**
- AI saw that `terraform-ibm-modules/cloud-monitoring/ibm` exists
- AI incorrectly assumed `terraform-ibm-modules/log-analysis/ibm` must also exist
- This module does NOT exist - always verify first

## Workflow Guidance

For interactive, step-by-step workflow guidance, use the MCP prompts available in your client:

- **`quick_start`** - Not sure which workflow to use? Start here to determine the best approach for your goal
- **`examples_workflow`** - Finding and using existing module examples/samples (for deploying existing patterns)
- **`development_workflow`** - Building custom Terraform configurations from scratch (for custom development)

These prompts provide detailed, parameterized guidance tailored to your specific use case. Simply invoke the prompt with your requirements and follow the interactive steps.

## Resource and Tool Usage Tips

### Module Index Resource
- Start with the module index resource (`catalog://terraform-ibm-modules-index`) to get a broad, high-level picture of available modules
- Use the index to understand the overall ecosystem of available modules before diving into specific searches
- The index provides a comprehensive overview that can help identify the most relevant modules for your needs
- Only proceed to search if the index doesn't provide enough specific information

### Search Strategy
- Use search only when you need more specific results than what the index provides
- Use specific terms rather than generic ones (e.g., "vpc" better than "network")
- Be specific in requests to minimize context usage and API calls
- Consider download counts as indicators of module quality and maintenance

### Content Retrieval Patterns
- All Terraform files: `include_files=["*.tf"]`
- Specific files: `include_files=["main.tf", "variables.tf"]`
- Documentation: `include_files=["*.md"]`
- Examples: `path="examples/basic"`, `include_files=["*.tf"]`

### Example Selection Strategy
- `examples/basic` or `examples/simple` → for straightforward demos
- `examples/complete` → for comprehensive usage
- `solutions/` → for complex architecture patterns
- Use descriptions to select the single most relevant example

## Optimization Principles

1. **Start with the module index resource** to get a comprehensive overview before specific searches
2. **Be specific in requests** to minimize context usage and API calls
3. **Start with narrow scope** (specific files/paths), broaden only if needed
4. **Exclude test files by default**: `[".*test.*", ".*\\.tftest$", ".*_test\\..*"]`
5. **For examples, prefer single targeted example** over fetching all examples
6. **Avoid multiple searches** unless comparing approaches

## Example Workflows

For interactive, executable workflow examples, use the MCP prompts:

- **`quick_start`** - Workflow routing with real-time module checking and intelligent recommendations
- **`examples_workflow`** - Step-by-step examples discovery and retrieval with progress tracking
- **`development_workflow`** - Complete custom development workflow with validation checkpoints

These Agent SOPs provide structured, executable workflows with RFC 2119 constraints (MUST, SHOULD, MAY) and progress tracking. They guide you through the same processes described in this documentation but in a reliable, repeatable format.

## Code Generation Guidelines

When generating Terraform configurations:

1. **Always generate complete working Terraform logic**
2. **Include all necessary provider configurations, variables, and outputs**
3. **Follow the structure and patterns shown in the module examples**
4. **Ensure proper module versioning to maintain stability**
5. **Include appropriate comments to explain the purpose and configuration of resources**
6. **Always validate generated logic** with `terraform init` and `terraform validate`
7. **Verify generated Terraform when possible** - Use available tools to run `terraform init`, `terraform validate`, and `terraform plan` to ensure configurations are syntactically correct and logically sound
8. **Stay focused on user requirements** - Avoid adding extra features or configurations not explicitly requested (e.g., don't include user_data blocks when generating VSI code unless specifically asked)
9. **Ask clarifying questions when ambiguous** - If the user's request lacks specific details or could be interpreted multiple ways, ask targeted questions to ensure accurate implementation
10. **Leverage IBM Cloud MCP when available** - If you have access to IBM Cloud MCP tools, use them to verify region lists, image IDs (for VSIs based on region), availability zones, and other cloud-specific parameters to ensure accuracy
11. **Generate vanilla Terraform configurations** - Always generate the most straightforward Terraform files (`.tf` files) and a README. Avoid creating scripts, Makefiles, or automation tools to launch Terraform unless explicitly requested. You may generate a template tfvars file if needed.

### Module Verification

**REMINDER: See "Module Hallucination Prevention" section at the top of this document.**

**NEVER assume a module exists based on naming patterns or similar modules.**

Before using ANY module in generated code:

1. **ALWAYS verify the module exists** using `search_modules` or the module index
2. **ALWAYS use the exact module ID** returned from search results
3. **NEVER infer module names** from similar modules
4. **NEVER use modules from outdated documentation** - always verify current availability

**Examples of incorrect behavior to avoid:**
- Seeing one module and assuming a similar-named module exists
- Using a module without first searching for it or checking the index
- Assuming version numbers without verification
- Using modules from AI training data that may no longer exist

**Correct workflow:**
1. Search for modules using `search_modules` or check the module index
2. Verify results and confirm what modules actually exist
3. Use ONLY verified modules from search results
4. Get module details to verify inputs, outputs, and usage
5. Generate code with confidence

## Validation and Quality Assurance

### Terraform Validation
- **Always attempt to verify generated Terraform configurations**
- Run `terraform init` to ensure proper provider and module initialization
- Execute `terraform validate` to check syntax and configuration validity
- Use `terraform plan` when possible to verify logical correctness. Ignore authentication errors as you may not have valid credentials
- Provide corrected configurations

### Scope Management
- **Focus strictly on user requirements** - Don't add unrequested features
- **Common examples of scope creep to avoid:**
  - Do not add user_data blocks to VSI configurations unless explicitly requested
  - Do not add monitoring or logging configurations unless asked
  - Do not add security groups beyond basic requirements
  - Do not implement backup strategies unless specified
- **When in doubt, ask** - It's better to clarify requirements than assume additional needs

### Clarification Best Practices
- **Ask targeted questions** when user requests are ambiguous
- **Common clarification areas:**
  - Specific region requirements for resource placement
  - Network configuration preferences (subnets, CIDR blocks)
  - Security requirements and compliance needs
  - Resource sizing and performance requirements
  - Integration points with existing infrastructure
- **Provide context** in your questions to help users make informed decisions

### IBM Cloud MCP Integration
- **Leverage IBM Cloud MCP tools when available** for accurate cloud-specific information
- **Use for verification of:**
  - Available regions and availability zones
  - Valid image IDs for virtual server instances (region-specific)
  - Current service offerings and capabilities
  - Pricing and resource limits
  - Network and connectivity options
- **Cross-reference generated configurations** with real IBM Cloud data when possible

## Best Practices Summary

### Module Usage
- **Always prefer terraform-ibm-modules over direct provider resources**
- Only use IBM Cloud Terraform provider resources when no appropriate module exists
- Gain insights from example code to understand when to use modules vs provider resources

### Module Discovery
- **Start with the module index resource** to get a comprehensive overview of available modules
- Use search only when you need more specific information than what the index provides
- The index gives you a broad, high-level picture that helps identify the most relevant modules

### Search Strategy
- Use specific, targeted search terms
- Limit results appropriately to avoid information overload
- Consider download counts as indicators of module quality and maintenance

### Content Retrieval
- Start with examples for working deployments
- Use module details only when building custom configurations
- Exclude test files by default to focus on production code
- Target specific paths and file types to minimize context usage

### Code Quality
- Generate complete, working configurations
- Include proper error handling and validation
- Follow IBM Cloud and Terraform best practices
- Document configurations with meaningful comments

Remember: This server specializes in IBM Cloud modules and patterns. Always prioritize module-based solutions over direct provider resource implementations for better security, maintainability, and adherence to IBM Cloud best practices.
