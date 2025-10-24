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
- **Use with**: `list_content` and `get_content` `path` parameter
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

## Workflow by Intent

The server supports two distinct workflows based on user intent:

### For Examples/Samples Workflow
**When users want existing deployments or working examples:**

Keywords to detect this intent: "example", "sample", "deploy", "show me", "simple"

1. First, check the **`catalog://terraform-ibm-modules-index`** resource to get a broad, high-level picture of available modules
2. If needed, use **`search_modules`** to find more specific modules (optional if the index provides enough information)
3. Use **`get_module_details`** to understand module capabilities using module ID from the index or search results
4. Use **`list_content`** to check what examples are available for the module
5. Use **`get_content`** to fetch example Terraform files (main.tf, provider.tf, version.tf)

The example files provide valuable insights:
- **Main configuration file**: Shows how to use and combine the module with others
- **Provider configuration file**: Demonstrates proper provider configuration
- **Version constraints file**: Shows required provider versions and constraints
- **Variables and outputs**: Define module interface and available values

Note: File names may vary (e.g., main.tf, provider.tf, version.tf, variables.tf, outputs.tf, etc.). Use `list_content` to see the actual file structure and names available in each example.

### For New Development Workflow
**When users need to write custom terraform:**

Keywords to detect this intent: "create", "build", "inputs", "outputs", "develop"

1. First, check the **`catalog://terraform-ibm-modules-index`** resource to get a broad, high-level picture of available modules
2. If needed, use **`search_modules`** to find more specific modules (optional if the index provides enough information)
3. Use **`get_module_details`** to understand inputs/outputs/interface using module ID from the index or search results
4. Use **`list_content`** to explore available examples and structure
5. Use **`get_content`** to fetch example files to understand usage patterns and provider setup

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

### Example 1: User Wants VPC Examples

**User Request:** "Show me a VPC example"
**Intent Detection:** Examples/Samples workflow (keywords: "show me", "example")

**Workflow:**
```
1. Check catalog://terraform-ibm-modules-index
   # Browse the index to identify relevant VPC modules
2. get_module_details("terraform-ibm-modules/landing-zone-vpc/ibm/8.4.0")
   # Understand module capabilities, inputs, outputs
3. list_content("terraform-ibm-modules/landing-zone-vpc/ibm/8.4.0")
   # Find available examples: examples/basic, examples/default, etc.
4. get_content("terraform-ibm-modules/landing-zone-vpc/ibm/8.4.0", "examples/basic", ["*.tf"])
   # Get configuration files showing module usage and provider setup
```

### Example 2: User Wants to Build Custom VPC Configuration

**User Request:** "I need to create a VPC with custom settings, what inputs does the module take?"
**Intent Detection:** Development workflow (keywords: "create", "inputs")

**Workflow:**
```
1. Check catalog://terraform-ibm-modules-index
   # Browse the index to identify relevant VPC modules
2. get_module_details("terraform-ibm-modules/landing-zone-vpc/ibm/8.4.0")
   # Get detailed inputs, outputs, and module interface
3. list_content("terraform-ibm-modules/landing-zone-vpc/ibm/8.4.0")
   # Check available examples for usage patterns
4. get_content("terraform-ibm-modules/landing-zone-vpc/ibm/8.4.0", "examples/basic", ["*.tf"])
   # Study example usage and provider configuration
5. [Generate custom configuration based on module interface and example patterns]
```

### Example 3: Complete Infrastructure Solution

**User Request:** "Create a VPC with subnets, security groups, and a cluster"
**Intent Detection:** Development workflow (keywords: "create")

**Workflow:**
```
1. Check catalog://terraform-ibm-modules-index
   # Browse the index to identify relevant modules for VPC, security groups, and clusters
2. search_modules("security group")
   # Optional: Search for specific security group modules if needed
3. search_modules("cluster")
   # Optional: Search for specific cluster modules if needed
4. get_module_details("terraform-ibm-modules/landing-zone-vpc/ibm/8.4.0")
5. get_module_details("terraform-ibm-modules/security-group/ibm/2.7.0")
6. get_module_details("terraform-ibm-modules/base-ocp-vpc/ibm/3.62.0")
7. list_content() for each module to find relevant examples
8. get_content() to examine example files showing module integration
9. [Generate complete Terraform combining all modules with proper provider setup]
```

### Example 4: Finding and Using Working Examples

**User Request:** "Show me how to deploy a complete VPC setup"
**Intent Detection:** Examples/Samples workflow (keywords: "show me", "deploy")

**Workflow:**
```
1. Check catalog://terraform-ibm-modules-index
   # Browse the index to identify relevant VPC modules
2. get_module_details("terraform-ibm-modules/landing-zone-vpc/ibm/8.4.0")
   # Understand what the module does and its capabilities
3. list_content("terraform-ibm-modules/landing-zone-vpc/ibm/8.4.0")
   # Find examples: basic, default, landing_zone, etc.
4. get_content("terraform-ibm-modules/landing-zone-vpc/ibm/8.4.0", "examples/default", ["*.tf"])
   # Get comprehensive example showing full VPC setup with provider configuration
```

### Example 5: Comparing Different Approaches

**User Request:** "What's the difference between basic and default VPC examples?"
**Intent Detection:** Examples/Samples workflow (keywords: "example")

**Workflow:**
```
1. Check catalog://terraform-ibm-modules-index
   # Browse the index to identify relevant VPC modules
2. get_module_details("terraform-ibm-modules/landing-zone-vpc/ibm/8.4.0")
   # Understand module interface
3. list_content("terraform-ibm-modules/landing-zone-vpc/ibm/8.4.0")
   # See all available examples: basic, default, custom_security_group, etc.
4. get_content("terraform-ibm-modules/landing-zone-vpc/ibm/8.4.0", "examples/basic", ["*.tf"])
   # Get basic example files
5. get_content("terraform-ibm-modules/landing-zone-vpc/ibm/8.4.0", "examples/default", ["*.tf"])
   # Get default example files for comparison
```

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
