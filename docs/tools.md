# MCP Tools Reference

TIM-MCP provides five tools designed for **efficient context gathering**. Each tool retrieves specific information to **minimize token usage** while **maximizing relevance**. The goal is to gather only the context needed for the user's task - no more, no less.

## Context Efficiency Strategy

- **Progressive disclosure**: Start with lightweight tools (`search_modules`, `list_content`) to understand what's available before fetching heavy content
- **Targeted retrieval**: Use filters (`include_files`, `exclude_files`) to fetch only relevant files
- **Smart caching**: Registry metadata (`get_module_details`, `get_example_details`) is faster than fetching source code
- **Choose wisely**: Examples are better than raw module details when available

## Quick Reference

| Tool | Context Weight | Primary Use |
|------|----------------|-------------|
| `search_modules` | Lightweight | Find module IDs (essential first step) |
| `list_content` | Lightweight | Discover what examples/content exist |
| `get_example_details` | Medium | Understand example without fetching code |
| `get_module_details` | Medium | Get module interface for custom builds |
| `get_content` | Heavy | Fetch actual source code (be selective!) |

## search_modules

Find modules in the Terraform Registry based on a search query.

**When to use:**
- User asks "what modules are available for X"
- User wants to find modules related to a specific IBM Cloud service
- Starting point for any module discovery

**Parameters:**
```
query (required): Search term like "vpc", "kubernetes", "observability"
limit (optional): Number of results, default 5
```

**Returns:** JSON with module IDs, descriptions, download counts, and verification status

**Example:**
```
search_modules(query="vpc", limit=5)
```

---

## get_module_details

Get structured module metadata from the Terraform Registry including inputs, outputs, dependencies, and requirements.

**When to use:**
- User wants to **write custom terraform** using a module
- User asks about "what inputs does this need", "what outputs", "what parameters"
- User is **building new configurations** from scratch

**When NOT to use:**
- User wants examples or sample code (use `list_content` + `get_content` instead)
- Examples exist and are more helpful than raw interface details

**Parameters:**
```
module_id (required):
  - "terraform-ibm-modules/vpc/ibm" (latest version)
  - "terraform-ibm-modules/vpc/ibm/7.19.0" (specific version)
```

**Returns:** Markdown with module description, required/optional inputs with types and defaults, outputs, provider requirements, and dependencies

**Example:**
```
get_module_details(module_id="terraform-ibm-modules/vpc/ibm")
```

---

## list_content

List the repository structure including available examples, submodules, and documentation.

**When to use:**
- User asks for "examples", "sample code", "how to use this module"
- First step before fetching any example code
- User wants to explore what's in the repository

**Parameters:**
```
module_id (required):
  - "terraform-ibm-modules/vpc/ibm" (latest version)
  - "terraform-ibm-modules/vpc/ibm/7.19.0" (specific version)
```

**Returns:** Markdown organized by category:
- **Examples**: Working deployment examples (most important for users wanting samples)
- **Root Module**: Main module files
- **Submodules**: Reusable components

Each item includes a description to help select the most relevant one.

**Example:**
```
list_content(module_id="terraform-ibm-modules/vpc/ibm")
```

**Tip:** When user wants examples, review the list and select the most appropriate one (e.g., `examples/basic` for simple use cases, `examples/complete` for comprehensive examples).

---

## get_example_details

Get detailed metadata about a specific example from the Terraform Registry **without fetching the full source code**. This is a context-efficient alternative to `get_content` when you need to understand what an example does.

**When to use:**
- After `list_content` shows available examples
- You want to verify an example matches user needs before fetching code (saves tokens!)
- User asks "what does this example need" or "what will this create"
- Multiple examples exist and you need to pick the right one

**Parameters:**
```
module_id (required):
  - "terraform-ibm-modules/vpc/ibm" (latest version)
  - "terraform-ibm-modules/vpc/ibm/7.19.0" (specific version)
example_path (required): Path from list_content like "examples/basic"
```

**Returns:** Markdown with:
- Example description and README
- Required and optional inputs with types and defaults
- Outputs produced
- Provider and module dependencies
- Resources created

**Example:**
```
get_example_details(
    module_id="terraform-ibm-modules/vpc/ibm",
    example_path="examples/basic"
)
```

**Context-efficient workflow:**
1. `list_content` - see what examples exist (lightweight)
2. `get_example_details` - verify it matches needs (medium, optional but recommended)
3. `get_content` - fetch only the necessary code (heavy, be selective with filters!)

---

## get_content

Fetch actual source code and files from the GitHub repository. **This is the heaviest tool** - use filters aggressively to minimize context pollution.

**When to use:**
- User wants to see actual terraform code
- After `list_content` identified the right example
- You've verified the content is relevant (via `get_example_details` or descriptions)

**Context efficiency tips:**
- Always use `include_files` to fetch only what's needed
- For examples, `include_files=["*.tf"]` excludes README and other docs
- For understanding usage, `include_files=["README.md", "main.tf"]` may be sufficient
- Avoid fetching test files, CI configs, or other irrelevant content

**Parameters:**
```
module_id (required):
  - "terraform-ibm-modules/vpc/ibm" (latest version)
  - "terraform-ibm-modules/vpc/ibm/7.19.0" (specific version)
path (optional):
  - "" (root, default)
  - "examples/basic"
  - "modules/submodule-name"
include_files (optional): List of glob patterns
  - ["*.tf"] - all Terraform files
  - ["main.tf", "variables.tf"] - specific files
  - ["*.md"] - all markdown files
exclude_files (optional): List of glob patterns to exclude
  - ["*test*"] - exclude test files
```

**Returns:** Markdown with file contents, organized by file with clear headers

**Common patterns (from most to least efficient):**

```
# Most efficient: Get only terraform files from an example
get_content(
    module_id="terraform-ibm-modules/vpc/ibm",
    path="examples/basic",
    include_files=["*.tf"]
)

# Targeted: Get specific files only
get_content(
    module_id="terraform-ibm-modules/vpc/ibm",
    path="examples/basic",
    include_files=["main.tf", "variables.tf"]
)

# Less efficient: Get all files (includes README, LICENSE, etc.)
# Only use when user specifically needs all context
get_content(
    module_id="terraform-ibm-modules/vpc/ibm",
    path="examples/basic"
)
```

---

## Version Support

All tools support both version formats:
- **Latest**: `terraform-ibm-modules/vpc/ibm` - uses the most recent published version
- **Pinned**: `terraform-ibm-modules/vpc/ibm/7.19.0` - uses a specific version

For production use cases, recommend pinned versions for consistency.

---

## Context-Efficient Workflows

### "Show me an example of X"
**Goal**: Get relevant example code with minimal context waste
1. `search_modules` - find module ID (lightweight)
2. `list_content` - see available examples (lightweight)
3. `get_example_details` - verify it's the right example (medium, recommended)
4. `get_content` with `include_files=["*.tf"]` - fetch only terraform files (heavy but filtered)

**Why this order?** Each step confirms relevance before fetching heavier content.

### "How do I use module X"
**Goal**: Provide usage guidance without fetching unnecessary files
1. `list_content` - find examples (lightweight)
2. `get_example_details` - get README and interface (medium)
3. Only call `get_content` if example details aren't sufficient

**Why?** Example details often contain enough information without fetching source code.

### "What inputs does module X need"
**Goal**: Get module interface only
1. `get_module_details` - get inputs/outputs from Registry (medium, direct from Registry)
2. Explain to user

**Don't** fetch source code - the Registry metadata is sufficient and faster.

### "Help me build terraform for X"
**Goal**: Provide starting point - prefer examples over raw interface
1. `search_modules` - find relevant modules (lightweight)
2. `list_content` - check if examples exist (lightweight)
3. Choose path:
   - **If examples exist** (preferred): `get_example_details` → `get_content` (filtered)
   - **If no examples**: `get_module_details` → help user build from scratch

**Why examples first?** Working code is better context than interface documentation.
