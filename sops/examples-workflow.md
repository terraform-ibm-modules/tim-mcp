# Examples Workflow SOP

## Description
This SOP guides you through finding and using existing Terraform IBM Module examples. Use this workflow when you want to deploy existing patterns or see working examples rather than building from scratch.

## Parameters

### Required Parameters
- **use_case**: What you want to deploy (e.g., "VPC", "Kubernetes cluster", "database")

### Optional Parameters
- **complexity**: Example complexity level - "basic" (default), "complete", or "solution"
  - "basic": Simple, straightforward demonstrations
  - "complete": Comprehensive usage with all features
  - "solution": Complex architecture patterns

## Workflow Steps

### Step 1: Module Discovery

**Objective**: Identify relevant Terraform IBM Modules for the use case.

**Actions**:
1. The agent MUST first access the `catalog://terraform-ibm-modules-index` MCP resource
2. The agent MUST review the module index to identify modules relevant to {use_case}
3. The agent SHOULD note module names, descriptions, and download counts
4. The agent MAY use `search_modules` tool if the index doesn't provide sufficient detail

**Validation**:
- The agent MUST confirm at least one relevant module was found before proceeding
- The agent MUST verify the exact module ID format (e.g., `terraform-ibm-modules/vpc/ibm`)

**Progress Tracking**:
```
✅ Reviewed module index for {use_case}
✅ Identified N relevant module(s): [list module IDs]
```

### Step 2: Module Analysis

**Objective**: Understand the capabilities and requirements of identified modules.

**Actions**:
1. For each relevant module identified in Step 1:
   - The agent MUST use `get_module_details` tool with the exact module ID
   - The agent SHOULD review the module description and purpose
   - The agent SHOULD note provider requirements and dependencies
   - The agent MUST document the module's key capabilities

**Constraints**:
- The agent MUST NOT assume module names based on patterns
- The agent MUST use the exact module ID from Step 1 results
- The agent MUST NOT proceed if `get_module_details` returns an error

**Progress Tracking**:
```
✅ Retrieved details for module: [module_id]
✅ Confirmed module provides: [key capabilities]
✅ Noted provider requirements: [requirements]
```

### Step 3: Example Discovery

**Objective**: Find available examples at the appropriate complexity level.

**Actions**:
1. The agent MUST use `list_content` tool with the module ID from Step 2
2. The agent MUST identify all available example paths in the repository
3. The agent SHOULD look for examples matching the {complexity} level:
   - For "basic": Look for `examples/basic`, `examples/simple`, or `examples/minimal`
   - For "complete": Look for `examples/complete`, `examples/default`, or `examples/full`
   - For "solution": Look for `solutions/` directories with architecture patterns
4. The agent MUST document the available example paths

**Fallback Behavior**:
- If no examples at the requested complexity level exist, the agent SHOULD recommend the closest available complexity level
- The agent MAY suggest multiple examples if they demonstrate different use cases

**Progress Tracking**:
```
✅ Listed repository contents for: [module_id]
✅ Found N example(s) at {complexity} level: [list paths]
```

### Step 4: Example Retrieval

**Objective**: Fetch the Terraform configuration files from the selected example.

**Actions**:
1. The agent MUST use `get_content` tool with:
   - `module_id`: The verified module ID from previous steps
   - `path`: The example path selected in Step 3
   - `include_files`: `["*.tf"]` to get all Terraform files
2. The agent MUST retrieve all Terraform files from the example
3. The agent SHOULD identify and note the purpose of each file:
   - `main.tf`: Primary module usage and resource configuration
   - `variables.tf`: Input variable definitions
   - `outputs.tf`: Output value definitions
   - `provider.tf`: Provider configuration
   - `version.tf` or `versions.tf`: Version constraints
   - `terraform.tf`: Terraform settings

**Validation**:
- The agent MUST confirm that at least `main.tf` was retrieved
- The agent SHOULD verify that provider configuration files exist

**Progress Tracking**:
```
✅ Retrieved Terraform files from: [example_path]
✅ Found N configuration files: [list files]
```

### Step 5: Example Analysis and Presentation

**Objective**: Analyze the example code and present findings to the user.

**Actions**:
1. The agent MUST analyze the retrieved Terraform files:
   - Identify how the module is instantiated and configured
   - Note required input variables and their purposes
   - Document available outputs
   - Identify provider configuration requirements
   - Note any dependencies on other modules or resources
2. The agent MUST present the analysis in a structured format:
   - Module usage pattern (from `main.tf`)
   - Required variables (from `variables.tf` and usage in `main.tf`)
   - Provider setup (from `provider.tf`)
   - Available outputs (from `outputs.tf`)
   - Version constraints (from `version.tf` or `versions.tf`)
3. The agent SHOULD provide guidance on:
   - How to customize the example for different use cases
   - What values need to be changed for the user's environment
   - Any prerequisites or setup required

**Best Practices**:
- The agent SHOULD explain the purpose of each configuration block
- The agent SHOULD highlight security-related configurations
- The agent MAY suggest improvements or alternatives

**Progress Tracking**:
```
✅ Analyzed example configuration
✅ Identified N required variables
✅ Documented module usage pattern
```

### Step 6: Summary and Next Steps

**Objective**: Provide a comprehensive summary and actionable next steps.

**Actions**:
1. The agent MUST provide a summary including:
   - Module(s) found for {use_case}
   - Example(s) retrieved at {complexity} level
   - Key configuration requirements
   - Provider and version requirements
2. The agent SHOULD provide next steps:
   - How to adapt the example for the user's specific needs
   - What values to customize
   - How to deploy the configuration
   - Where to find additional documentation
3. The agent MAY offer to:
   - Show different complexity levels
   - Explore different modules for the same use case
   - Help customize the example for specific requirements

**Progress Tracking**:
```
✅ Summary complete
✅ Next steps provided
✅ Ready for deployment or customization
```

## Important Reminders

Throughout this workflow:
- The agent MUST NEVER hallucinate or assume module names based on patterns
- The agent MUST ALWAYS verify modules exist using `search_modules` or the module index
- The agent MUST use exact module IDs from search results without modification
- The agent SHOULD prefer higher download count modules as they indicate better maintenance
- The agent MUST NOT proceed to the next step if validation fails in the current step

## Success Criteria

The workflow is complete when:
1. ✅ At least one relevant module has been identified and verified
2. ✅ Module details have been retrieved and analyzed
3. ✅ Example code at the appropriate complexity level has been found and retrieved
4. ✅ The example has been analyzed and explained to the user
5. ✅ Clear next steps have been provided for using the example
