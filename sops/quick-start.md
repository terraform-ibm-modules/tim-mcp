# Quick Start SOP

## Description
This SOP helps you determine the appropriate workflow for working with Terraform IBM Modules. Use this when you're unsure whether to use the Examples Workflow or Development Workflow.

## Parameters

### Required Parameters
- **goal**: What you want to accomplish (e.g., "deploy a VPC", "create infrastructure")

### Optional Parameters
- **has_existing_example**: Whether you want to use an existing example - "yes", "no", or "unknown" (default: "unknown")

## Workflow Steps

### Step 1: Goal Analysis

**Objective**: Understand the user's goal and context.

**Actions**:
1. The agent MUST analyze {goal} to understand:
   - What infrastructure needs to be created
   - Whether this is a common use case or custom requirement
   - The level of customization needed
2. The agent SHOULD identify keywords that indicate workflow preference:
   - Example-oriented: "show me", "example", "sample", "deploy", "how to", "simple"
   - Development-oriented: "create", "build", "custom", "specific", "design", "develop"
3. The agent MUST note the {has_existing_example} preference if provided

**Progress Tracking**:
```
✅ Analyzed goal: {goal}
✅ Identified infrastructure needs: [list]
✅ User preference: {has_existing_example}
```

### Step 2: Module Ecosystem Check

**Objective**: Determine if suitable modules exist for the goal.

**Actions**:
1. The agent MUST access the `catalog://terraform-ibm-modules-index` MCP resource
2. The agent MUST search for modules relevant to {goal}
3. The agent SHOULD assess:
   - Whether modules exist that directly address {goal}
   - Whether examples are likely available (indicated by popular modules)
   - Whether multiple modules will need to be composed
4. The agent MAY use `search_modules` tool for targeted verification

**Validation**:
- The agent MUST confirm relevant modules exist before recommending a workflow

**Progress Tracking**:
```
✅ Checked module index for: {goal}
✅ Found N relevant module(s)
✅ Assessed example availability
```

### Step 3: Workflow Recommendation

**Objective**: Recommend the appropriate workflow based on analysis.

**Actions**:
1. The agent MUST determine the recommended workflow using this logic:

   **Recommend Examples Workflow when**:
   - {has_existing_example} is "yes", OR
   - {goal} contains example-oriented keywords ("show me", "example", "sample"), OR
   - The use case is straightforward and popular modules with examples exist, OR
   - The user wants to deploy quickly without extensive customization

   **Recommend Development Workflow when**:
   - {has_existing_example} is "no", OR
   - {goal} contains development-oriented keywords ("create", "build", "custom"), OR
   - The requirements are highly specific or custom, OR
   - Multiple modules need to be composed in a non-standard way, OR
   - Significant customization beyond examples is needed

   **Request clarification when**:
   - {has_existing_example} is "unknown", AND
   - {goal} is ambiguous about which workflow is appropriate, AND
   - Both workflows seem equally suitable

2. The agent MUST provide a clear recommendation with rationale
3. The agent SHOULD explain what the recommended workflow will do
4. The agent MAY mention the alternative workflow and when to use it

**Constraints**:
- The agent MUST recommend exactly one workflow (or request clarification)
- The agent MUST provide reasoning for the recommendation

**Progress Tracking**:
```
✅ Analyzed workflow suitability
✅ Recommended: [Examples Workflow | Development Workflow | Need Clarification]
✅ Provided rationale
```

### Step 4: Workflow Overview

**Objective**: Explain the recommended workflow and what to expect.

**Actions**:
1. If recommending **Examples Workflow**:
   - The agent MUST explain that this workflow will:
     - Find relevant modules from the TIM ecosystem
     - Locate existing examples at the appropriate complexity
     - Retrieve and explain example Terraform code
     - Guide adaptation for the user's specific needs
   - The agent SHOULD mention the `examples_workflow` prompt
   - The agent SHOULD provide example parameters:
     - `use_case`: [extracted from {goal}]
     - `complexity`: "basic" (or suggest appropriate level)

2. If recommending **Development Workflow**:
   - The agent MUST explain that this workflow will:
     - Identify all required modules for the requirements
     - Analyze module interfaces (inputs/outputs)
     - Design the configuration architecture
     - Generate complete Terraform files from scratch
     - Create comprehensive documentation
   - The agent SHOULD mention the `development_workflow` prompt
   - The agent SHOULD provide example parameters:
     - `requirement`: [extracted from {goal}]

3. If requesting **clarification**:
   - The agent MUST ask specific questions to determine the right workflow:
     - "Do you want to start from an existing example or build from scratch?"
     - "Do you need extensive customization or is a standard pattern sufficient?"
     - "Are you looking for a quick start or full control over the design?"
   - The agent SHOULD explain the key differences between workflows
   - The agent MUST wait for user response before proceeding

**Progress Tracking**:
```
✅ Explained recommended workflow
✅ Provided next steps
✅ Ready to proceed
```

### Step 5: Next Steps and Handoff

**Objective**: Guide the user to invoke the appropriate workflow.

**Actions**:
1. The agent MUST provide clear next steps:
   - For Examples Workflow: Invoke `examples_workflow` prompt with parameters
   - For Development Workflow: Invoke `development_workflow` prompt with parameters
   - For Clarification: Wait for user response, then re-run this SOP

2. The agent SHOULD provide a command template:
   ```
   [Examples Workflow]
   @examples_workflow
   use_case: [extracted from goal]
   complexity: basic

   [Development Workflow]
   @development_workflow
   requirement: [extracted from goal]
   ```

3. The agent MAY offer to invoke the workflow directly if that capability exists

4. The agent SHOULD remind about key TIM principles:
   - Always verify modules exist before using them
   - Never assume module names based on patterns
   - Prefer TIM modules over direct provider resources
   - Use exact module IDs from search results

**Progress Tracking**:
```
✅ Provided workflow invocation instructions
✅ Prepared parameters
✅ Reminded of key principles
```

## Important Reminders

Throughout this workflow:
- The agent MUST make a clear recommendation or request clarification
- The agent MUST NOT proceed to execute the chosen workflow automatically
- The agent SHOULD help extract parameters from {goal} for the next workflow
- The agent MUST explain the rationale for the recommendation
- The agent SHOULD set appropriate expectations for what the workflow will accomplish

## Success Criteria

The workflow is complete when:
1. ✅ The user's goal has been analyzed
2. ✅ The module ecosystem has been checked for relevance
3. ✅ A workflow has been recommended (or clarification requested)
4. ✅ The recommended workflow has been explained
5. ✅ Clear next steps have been provided with parameters
6. ✅ The user understands which prompt to invoke next
