# MCP Tools Reference

TIM-MCP provides multiple tools designed for **efficient context gathering**. Each tool retrieves specific information to **minimize token usage** while **maximizing relevance**. The goal is to gather only the context needed for the user's task - no more, no less.

## Context Efficiency Strategy

- **Progressive disclosure**: Start with lightweight tools (`search_modules`, `list_content`) to understand what's available before fetching heavy content
- **Targeted retrieval**: Use filters (`include_files`, `exclude_files`) to fetch only relevant files
- **Smart caching**: Registry metadata (`get_module_details`, `get_example_details`) is faster than fetching source code
- **Choose wisely**: Examples are better than raw module details when available

## Quick Reference

| Tool | Context Weight | Primary Use |
|------|----------------|-------------|
| `generate_module_composition` | Heavy | Assemble a composition JSON from a prompt (calls the other tools live) |
| `search_modules` | Lightweight | Find module IDs (essential first step) |
| `get_latest_module_version` | Lightweight | Get the newest published module version and release info |
| `list_content` | Lightweight | Discover what examples/content exist |
| `get_example_details` | Medium | Understand example without fetching code |
| `get_module_details` | Medium | Get module interface for custom builds |
| `get_module_dependency` | Medium | Inspect provider and module dependencies |
| `get_content` | Heavy | Fetch actual source code or submodule input/output schemas (be selective!) |

## search_modules

Find Terraform modules based on a module name, service category, or relevant multi-word description phrases.

**When to use:**
- User asks "what modules are available for X"
- User wants to find modules related to a specific IBM Cloud service or category
- Starting point for any module discovery

**Parameters:**
```
query (required): Module name, service category, or relevant multi-word description phrases(eg:,"vpc", "networking", "secrets manager")
limit (optional): Number of results, default 5
```

**Returns:** JSON with module IDs, descriptions, download counts, and verification status

**Search Behaviour:**
- Searches the `static/module_index.json` first for fast results.
- If the index returns fewer results than the requested limit or no results, searches the live Terraform Registry.
- Results are merged, deduplicated by module_id, and ranked by download count.

**Example:**
```
search_modules(query="vpc", limit=5)
```

---

## generate_module_composition

Assemble a composition for a natural-language request by calling the *other* TIM-MCP tools live. Given a prompt naming a pattern and the pieces to include (e.g. "gimme an openshift composition with kms and cos"), it returns a **composition JSON** — the modules, deployment order, wiring, and prerequisites — built entirely from live registry data. This is the entry point for AI-assisted, multi-module composition.

It holds **no static module data**. Module IDs and versions come from `search_modules`; connections are derived from the real interfaces read via `get_module_details`; and when a DA is requested, a `reference_solution` pointer to the deployable architecture is added (fetch it with `get_content` for the authoritative wiring). The result always reflects the current registry.

**When to use:**
- User asks "how do I build X on IBM Cloud" or "give me an X composition with Y and Z"
- Starting a new multi-module Terraform solution around a service

**Note:** this tool makes live registry/GitHub calls per request (search + details for every module), so it is **slower** than the lightweight tools — expect a few seconds per module.

**Parameters:**
```
services (preferred): The services to compose, as plain terms you extracted from
  the user's request, e.g. ["openshift", "kms", "cos"]. Each is resolved to a real
  module — more reliable than having the tool re-parse free text.
prompt (fallback): Natural-language request, used when `services` is not given, e.g.
  "gimme an openshift composition with kms and cos". Mention "DA" for DA grounding.
include_da (optional): true to add a deployable-architecture reference_solution pointer.
```
Provide `services` or `prompt` (at least one).

**Returns:** JSON with:
- `composition_name`, `description` (one-line summary), `prompt`, `da_grounded`
- `reference_solution`: the anchor DA (`module_id`, `solution_path`, `source_url`) — only present when `da_grounded`
- `recommended_modules`: each with `id`, `instance_name`, `role` (foundation/support/workload), `purpose` (the module's live registry description), resolved `version`, `source`, `registry_url` (all from `search_modules`)
- `deployment_order`: instance names in dependency order
- `connections`: `source_module.source_output` → `target_module.target_input` (`origin: "inferred"`) — derived from matching module interfaces (approximate; verify with `get_module_details`)
- `prerequisites`: top-level inputs to supply (api key, region, resource group, prefix)
- `notes`: caveats and unresolved items (e.g. an encryption input that couldn't be auto-wired)

**DA grounding is opt-in:** when the prompt mentions "DA" (or "deployable architecture"), the response includes a `reference_solution` pointer to the module's deployable-architecture `solutions/` directory. Connections are always inferred from interfaces — real DAs route their wiring through locals/interpolation that can't be extracted reliably, so `reference_solution` points you at the authoritative wiring (fetch it with `get_content`) rather than the tool guessing it.

**Example:**
```
generate_module_composition(prompt="gimme an openshift composition with kms and cos")
```

**How to use the result:** emit one `module` block per `recommended_modules` entry (registry `source` + `version`), wire each `connections` entry as `target_input = module.<source_module>.<source_output>`, and surface `prerequisites` as root variables. Treat `inferred` connections as suggestions — confirm exact input/output names with `get_module_details` before finalizing.

---

## get_latest_module_version

Get the latest published module version for a module and include GitHub release metadata when a release exists.

**When to use:**
- User asks for the latest version of a known module
- User wants release-related information before pinning a version
- You need a targeted on-demand version lookup instead of browsing the static module index

**Parameters:**
```
module_id (required):
  - "terraform-ibm-modules/vpc/ibm" (preferred)
  - "terraform-ibm-modules/vpc/ibm/7.19.0" (accepted, but latest published version is still returned)
```

**Returns:** Markdown with:
- Latest published module version
- GitHub release tag, name, publication date, and release URL when available
- Release notes when available
- A fallback message when the repository has no GitHub release data

**Example:**
```
get_latest_module_version(module_id="terraform-ibm-modules/vpc/ibm")
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

## get_module_dependency

Get all required provider requirements and module dependencies for a Terraform module, covering the root module and every submodule.

**When to use:**
- User asks "what does this module depend on?"
- To check required providers before adding a module to an existing stack
- To understand transitive dependencies across submodules

**Parameters:**
```
module_id (required):
  - "terraform-ibm-modules/vpc/ibm" (latest version)
  - "terraform-ibm-modules/vpc/ibm/7.19.0" (specific version)
```

**Returns:** Markdown with:
- Root module provider requirements (name and version constraint)
- Root module module dependencies (name, version, and source)
- Per-submodule provider and module dependency breakdown

**Example:**
```
get_module_dependency(module_id="terraform-ibm-modules/vpc/ibm")
```

---

## get_content

Fetch actual source code and files from the GitHub repository. **This is the heaviest tool** - use filters aggressively to minimize context pollution.

**When to use:**
- User wants to see actual terraform code
- After `list_content` identified the right example
- You've verified the content is relevant (via `get_example_details` or descriptions)
- User asks about inputs or outputs of a **submodule** (use `path="modules/<submodule-name>"` with `include_files=["variables.tf", "outputs.tf"]`)

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

# Submodule schemas: get input/output schema for a submodule
# Returns variables.tf, outputs.tf
# Use list_content first to discover available submodule paths
get_content(
    module_id="terraform-ibm-modules/vpc/ibm",
    path="modules/submodule-name",
    include_files=["variables.tf", "outputs.tf"]
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

**For root module:**
1. `get_module_details` - get inputs/outputs from Registry (medium, direct from Registry)
2. Explain to user

**Don't** fetch source code for the root module - the Registry metadata is sufficient and faster.

**For a submodule:**
1. `list_content` - identify the submodule path under the **Submodules** section (lightweight)
2. `get_content` with `path="modules/<submodule-name>"` and `include_files=["variables.tf", "outputs.tf"]` - fetches the schema files and generates a Configuration Summary (heavy but targeted)

### "Help me build terraform for X"
**Goal**: Provide starting point - prefer examples over raw interface
1. `search_modules` - find relevant modules (lightweight)
2. `list_content` - check if examples exist (lightweight)
3. Choose path:
   - **If examples exist** (preferred): `get_example_details` → `get_content` (filtered)
   - **If no examples**: `get_module_details` → help user build from scratch

**Why examples first?** Working code is better context than interface documentation.

### "Build a full architecture for X" (multi-module composition)
**Goal**: Wire several modules together into a working solution
1. `generate_module_composition` - returns a composition JSON assembled live (modules + versions from `search_modules`, wiring derived from interfaces, or from the DA when the prompt says "DA"); heavier, a few seconds per module
2. Review the `connections` — `origin: "da"` are authoritative; `origin: "inferred"` are approximate, so confirm those with `get_module_details` (medium)
3. Generate the Terraform: one `module` block per `recommended_modules` entry (registry `source` + `version`), wiring each `connections` entry as `target_input = module.<source_module>.<source_output>`, and surfacing `prerequisites` as root variables. Address anything in `notes` (e.g. an unwired encryption input).

**Why start here?** Everything — module IDs, versions, and wiring — comes from live discovery, so nothing is hardcoded to go stale.
