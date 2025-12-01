# Development Workflow SOP

## Description
This SOP guides you through building custom Terraform configurations using Terraform IBM Modules. Use this workflow when you need to create infrastructure from scratch with specific requirements rather than using existing examples.

## Parameters

### Required Parameters
- **requirement**: What you need to build (e.g., "custom VPC with 3 subnets", "multi-region infrastructure")

### Optional Parameters
- **documentation_dir**: Directory for planning documents (default: ".sop/planning")
- **repo_root**: Root directory of the repository (default: current working directory)

## Workflow Steps

### Step 1: Requirement Analysis and Module Discovery

**Objective**: Understand the requirements and identify necessary Terraform IBM Modules.

**Actions**:
1. The agent MUST analyze {requirement} to identify needed infrastructure components
2. The agent MUST access the `catalog://terraform-ibm-modules-index` MCP resource
3. The agent MUST identify all modules needed to fulfill {requirement}
4. The agent MAY use `search_modules` tool for targeted searches of specific components
5. The agent MUST document the list of modules with their purposes

**Validation**:
- The agent MUST confirm each identified module actually exists
- The agent MUST verify module IDs are in the correct format
- The agent MUST NOT assume module names based on patterns

**Progress Tracking**:
```
✅ Analyzed requirement: {requirement}
✅ Identified N component(s) needed: [list components]
✅ Found N module(s): [list module IDs]
```

### Step 2: Module Interface Analysis

**Objective**: Understand the inputs, outputs, and capabilities of each required module.

**Actions**:
1. For each module identified in Step 1:
   - The agent MUST use `get_module_details` tool with the exact module ID
   - The agent MUST document all required inputs and their types
   - The agent MUST document all optional inputs and their defaults
   - The agent MUST document all outputs available for composition
   - The agent SHOULD note provider version requirements
   - The agent SHOULD identify dependencies on other modules or resources
2. The agent MUST create a module interface summary including:
   - Required inputs per module
   - Optional inputs that may be relevant to {requirement}
   - Outputs that can be used as inputs to other modules
   - Inter-module dependencies and composition patterns

**Constraints**:
- The agent MUST NOT proceed without understanding required inputs
- The agent MUST verify compatibility of provider versions across modules

**Progress Tracking**:
```
✅ Retrieved details for N modules
✅ Documented required inputs: [count by module]
✅ Documented available outputs: [count by module]
✅ Identified composition patterns
```

### Step 3: Example Pattern Study

**Objective**: Learn from existing implementations to understand best practices.

**Actions**:
1. For each module from Step 1:
   - The agent MUST use `list_content` tool to discover available examples
   - The agent SHOULD identify the most relevant example for {requirement}
   - The agent SHOULD use `get_content` tool to retrieve at least one example per module
2. The agent MUST analyze example patterns for:
   - How modules are instantiated and configured
   - Provider configuration patterns
   - Variable definition patterns
   - How modules are composed together
   - Common configuration values and patterns
3. The agent SHOULD note best practices observed in examples:
   - Naming conventions
   - Resource tagging patterns
   - Security configurations
   - Network architecture patterns

**Validation**:
- The agent SHOULD verify at least one example was retrieved per module
- The agent MAY skip examples if module documentation is sufficient

**Progress Tracking**:
```
✅ Retrieved N examples across modules
✅ Identified common patterns: [list patterns]
✅ Noted best practices: [list practices]
```

### Step 4: Architecture Design

**Objective**: Design the custom Terraform configuration architecture.

**Actions**:
1. The agent MUST design the module composition:
   - Determine how modules will be connected (output → input mappings)
   - Identify shared values and local variables
   - Plan resource naming strategy
   - Design variable structure for user customization
2. The agent MUST create an architecture plan including:
   - Module instantiation order and dependencies
   - Data flow between modules (outputs to inputs)
   - Shared configuration values
   - Required provider configuration
3. The agent SHOULD document the plan in {documentation_dir}:
   - Create `architecture.md` with overall design
   - Document module composition diagram (as text/markdown)
   - List all required and optional variables
   - Define output structure

**Constraints**:
- The agent MUST ensure all required inputs will have values
- The agent MUST verify output → input type compatibility
- The agent SHOULD minimize redundant variables

**Progress Tracking**:
```
✅ Designed module composition
✅ Mapped N output→input connections
✅ Created architecture documentation
✅ Defined variable structure
```

### Step 5: Configuration Generation

**Objective**: Generate the Terraform configuration files.

**Actions**:
1. The agent MUST generate the following files in {repo_root}:

   **main.tf**:
   - The agent MUST instantiate each required module
   - The agent MUST configure all required inputs
   - The agent SHOULD configure relevant optional inputs
   - The agent MUST wire outputs to inputs as designed
   - The agent SHOULD add comments explaining each module's purpose

   **variables.tf**:
   - The agent MUST define all variables needed by the configuration
   - The agent MUST include type constraints
   - The agent MUST provide descriptions for each variable
   - The agent SHOULD provide sensible defaults where appropriate
   - The agent SHOULD group related variables

   **outputs.tf**:
   - The agent MUST expose key outputs from the modules
   - The agent MUST provide descriptions for each output
   - The agent SHOULD expose outputs needed for further composition

   **provider.tf** or **providers.tf**:
   - The agent MUST configure required providers
   - The agent MUST match provider versions to module requirements
   - The agent SHOULD use provider aliases if needed for multi-region

   **versions.tf** or **terraform.tf**:
   - The agent MUST specify Terraform version constraints
   - The agent MUST specify required providers and versions
   - The agent SHOULD use versions compatible with all modules

2. The agent SHOULD follow these patterns from examples:
   - Use consistent naming conventions
   - Apply appropriate tagging strategies
   - Include security best practices
   - Use local values to reduce duplication

**Constraints**:
- The agent MUST use exact module sources from the Terraform Registry
- The agent MUST pin module versions for stability
- The agent MUST NOT use hardcoded secrets or credentials
- The agent SHOULD validate Terraform syntax as it generates

**Progress Tracking**:
```
✅ Generated main.tf with N module(s)
✅ Created variables.tf with N variable(s)
✅ Created outputs.tf with N output(s)
✅ Configured provider(s): [list providers]
✅ Set version constraints
```

### Step 6: Configuration Validation

**Objective**: Validate the generated Terraform configuration.

**Actions**:
1. The agent SHOULD attempt to validate the configuration:
   - Run `terraform fmt` to ensure proper formatting
   - Run `terraform init` to download providers and modules
   - Run `terraform validate` to check syntax and configuration
2. The agent MUST review validation results:
   - Document any errors or warnings
   - Fix syntax errors if found
   - Suggest corrections for configuration issues
3. The agent MAY attempt a plan if credentials are available:
   - Run `terraform plan` to verify logical correctness
   - Document the plan output
   - Note: Authentication errors are acceptable at this stage

**Fallback**:
- If tools are not available, the agent SHOULD perform manual syntax review
- The agent SHOULD check for common mistakes (missing required arguments, type mismatches)

**Progress Tracking**:
```
✅ Formatted configuration files
✅ Initialized Terraform (or skipped if unavailable)
✅ Validated configuration (or manually reviewed)
✅ Addressed N issues found
```

### Step 7: Documentation and Next Steps

**Objective**: Provide comprehensive documentation and guidance for using the configuration.

**Actions**:
1. The agent MUST create a `README.md` in {repo_root} that includes:
   - Purpose and overview of the infrastructure
   - Prerequisites (IBM Cloud account, API key, etc.)
   - Required variables and how to set them
   - Step-by-step usage instructions
   - Example variable values (without sensitive data)
   - Expected outputs and their meanings
   - Customization guidance
2. The agent SHOULD create a `terraform.tfvars.example` file:
   - Include all required variables with placeholder values
   - Include commonly used optional variables
   - Add comments explaining what values to provide
3. The agent MUST provide next steps:
   - How to customize the configuration for specific needs
   - How to deploy the infrastructure
   - How to manage and update the deployment
   - Where to find additional documentation
4. The agent SHOULD offer to:
   - Explain specific parts of the configuration
   - Add additional features or modules
   - Generate deployment scripts or automation

**Progress Tracking**:
```
✅ Created comprehensive README.md
✅ Generated terraform.tfvars.example
✅ Documented customization options
✅ Provided deployment instructions
```

### Step 8: Summary and Handoff

**Objective**: Summarize the work and ensure the user understands the deliverables.

**Actions**:
1. The agent MUST provide a summary including:
   - What was built to fulfill {requirement}
   - Modules used and their purposes
   - Files generated and their locations
   - Key configuration points
   - Validation status
2. The agent MUST list the deliverables:
   - main.tf, variables.tf, outputs.tf, provider.tf, versions.tf
   - README.md and terraform.tfvars.example
   - Architecture documentation (if created)
3. The agent SHOULD highlight:
   - Security considerations
   - Cost implications (if known)
   - Operational considerations
   - Testing recommendations
4. The agent MUST confirm the user understands:
   - How to customize the configuration
   - What values need to be provided
   - How to deploy and manage the infrastructure

**Progress Tracking**:
```
✅ Generated N Terraform files
✅ Created documentation
✅ Validated configuration (if possible)
✅ Ready for customization and deployment
```

## Important Reminders

Throughout this workflow:
- The agent MUST NEVER assume modules exist - always verify first
- The agent MUST use exact module IDs from search results without modification
- The agent MUST prefer terraform-ibm-modules over direct provider resources
- The agent MUST pin module versions for production stability
- The agent SHOULD stay focused on {requirement} without scope creep
- The agent MUST NOT include hardcoded credentials or secrets
- The agent SHOULD follow IBM Cloud and Terraform best practices

## Success Criteria

The workflow is complete when:
1. ✅ All required modules have been identified and verified
2. ✅ Module interfaces (inputs/outputs) have been documented
3. ✅ Configuration architecture has been designed
4. ✅ Complete Terraform files have been generated
5. ✅ Configuration has been validated (or reviewed if tools unavailable)
6. ✅ Comprehensive documentation has been created
7. ✅ User understands how to customize and deploy the configuration
