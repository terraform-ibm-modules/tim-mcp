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

The main purpose of this MCP server is to help generate terraform-based compositions of modules. It provides tools to:

1. Search for relevant Terraform IBM Modules
2. Discover available examples and repository structure
3. Get detailed information about modules, including inputs, outputs, and examples
4. Access example code and specific files to understand how to use and combine modules
5. Generate complete, working Terraform configurations

## Architectural Best Practices

**ALWAYS prefer terraform-ibm-modules over direct provider resources**

Modules provide:
- Security hardening
- Standardized configurations
- Tested patterns
- Best practices implementation

Use direct provider resources only when no suitable module exists.

## Provider Tools Scope and Usage

### Allowlisted Providers
The provider search and details tools are restricted to these allowlisted providers:
- **HashiCorp utility providers** - Essential utility providers for common Terraform patterns:
  - `hashicorp/time` - Time-based resources and delays
  - `hashicorp/null` - Null resources for triggers and dependencies
  - `hashicorp/local` - Local file operations
  - `hashicorp/kubernetes` - Kubernetes resource management
  - `hashicorp/random` - Random value generation
  - `hashicorp/helm` - Helm chart deployment
  - `hashicorp/external` - External data sources and program execution
- **Mastercard/restapi** - REST API provider for filling IBM Cloud provider functionality gaps
- **IBM-Cloud/ibm** - Primary provider for IBM Cloud resources

### Provider Usage Hierarchy
When working with IBM Cloud infrastructure, follow this priority order:

1. **FIRST: Use Terraform IBM Modules (TIM)**
   - Always start by searching for relevant TIM modules
   - TIM modules provide tested, secure, and standardized patterns

2. **SECOND: Use IBM Cloud Provider (IBM-Cloud/ibm)**
   - Use for IBM Cloud resources not covered by TIM modules
   - Primary provider for all IBM Cloud infrastructure

3. **THIRD: Use restapi Provider (Mastercard/restapi) - SPARINGLY**
   - **ONLY** use to fill functionality gaps in the IBM Cloud provider
   - This is a supplementary tool, not a primary solution
   - Always document why the IBM Cloud provider was insufficient

4. **UTILITY: HashiCorp Utility Providers**
   - Use for cross-platform infrastructure needs
   - Examples: time delays, random IDs, null resources for triggers
   - These are utility providers, not primary infrastructure providers

### When to Use Provider Tools
- To stitch together TIM modules that require provider configuration
- To fill specific gaps where no TIM module exists
- To understand provider version requirements for TIM modules
- For utility functions like random generation or time-based resources
- For Kubernetes/Helm management alongside IBM Cloud infrastructure

### Important Constraints
- Only allowlisted providers are accessible through these tools
- The restapi provider should be a last resort, not a primary tool
- HashiCorp providers are limited to utility functions only (no cloud providers like AWS, Azure, GCP)
- Always prefer module-based solutions over raw provider resources

## Workflow by Intent

The server supports two distinct workflows based on user intent:

### For Examples/Samples Workflow
**When users want existing deployments or working examples:**

Keywords to detect this intent: "example", "sample", "deploy", "show me", "simple"

1. **`search_modules`** → Find relevant modules
2. **`get_module_details`** → Understand module capabilities using module ID from search results
3. **`list_content`** → Check what examples are available for the module
4. **`get_content`** → Fetch example Terraform files (main.tf, provider.tf, version.tf)

The example files provide valuable insights:
- **Main configuration file**: Shows how to use and combine the module with others
- **Provider configuration file**: Demonstrates proper provider configuration
- **Version constraints file**: Shows required provider versions and constraints
- **Variables and outputs**: Define module interface and available values

Note: File names may vary (e.g., main.tf, provider.tf, version.tf, variables.tf, outputs.tf, etc.). Use `list_content` to see the actual file structure and names available in each example.

### For New Development Workflow
**When users need to write custom terraform:**

Keywords to detect this intent: "create", "build", "inputs", "outputs", "develop"

1. **`search_modules`** → Find relevant modules
2. **`get_module_details`** → Understand inputs/outputs/interface using module ID from search results
3. **`list_content`** → Explore available examples and structure
4. **`get_content`** → Fetch example files to understand usage patterns and provider setup

## Tool Usage Tips

### Search Strategy
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

1. **Be specific in requests** to minimize context usage and API calls
2. **Start with narrow scope** (specific files/paths), broaden only if needed
3. **Exclude test files by default**: `[".*test.*", ".*\\.tftest$", ".*_test\\..*"]`
4. **For examples, prefer single targeted example** over fetching all examples
5. **Avoid multiple searches** unless comparing approaches

## Example Workflows

### Example 1: User Wants VPC Examples

**User Request:** "Show me a VPC example"
**Intent Detection:** Examples/Samples workflow (keywords: "show me", "example")

**Workflow:**
```
1. search_modules("vpc")
   # Returns: terraform-ibm-modules/landing-zone-vpc/ibm/8.4.0 (among others)
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
1. search_modules("vpc")
   # Returns: terraform-ibm-modules/landing-zone-vpc/ibm/8.4.0 (among others)
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
1. search_modules("vpc")
   # Returns: terraform-ibm-modules/landing-zone-vpc/ibm/8.4.0, etc.
2. search_modules("security group")
   # Returns: terraform-ibm-modules/security-group/ibm/2.7.0, etc.
3. search_modules("cluster")
   # Returns: terraform-ibm-modules/base-ocp-vpc/ibm/3.62.0, etc.
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
1. search_modules("vpc")
   # Returns: terraform-ibm-modules/landing-zone-vpc/ibm/8.4.0, etc.
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
1. search_modules("vpc")
   # Returns: terraform-ibm-modules/landing-zone-vpc/ibm/8.4.0, etc.
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
