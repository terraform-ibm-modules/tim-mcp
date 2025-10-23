# Issue #31: Module Hallucination - Summary and Fix

## Issue Description

The AI hallucinated a module `terraform-ibm-modules/log-analysis/ibm` version 1.9.2 that doesn't exist in the Terraform Registry, and used it in generated code.

## Root Cause Analysis

### What Actually Exists
When searching for "log" or "log analysis" in the Terraform Registry:
- ✅ `terraform-ibm-modules/observability-instances/ibm` - Handles Log Analysis, Activity Tracker, Monitoring, and Cloud Logs
- ✅ `terraform-ibm-modules/cloud-monitoring/ibm` - Handles IBM Cloud Monitoring
- ❌ `terraform-ibm-modules/log-analysis/ibm` - **DOES NOT EXIST**

### Why the Hallucination Occurred

The AI inferred a module name based on:
1. **Pattern matching**: Saw `cloud-monitoring` and assumed `log-analysis` should exist
2. **Naming convention assumption**: Assumed IBM follows a pattern of one module per service
3. **Training data**: May have been trained on documentation or examples that referenced modules that no longer exist

### Relationship to Issue #21

Initially, we thought this might be related to issue #21 (total_found incorrectly set to 0), but:
- Issue #21 was about the MCP server returning `total_found=0` when modules DO exist
- Issue #31 is about the AI hallucinating modules that DON'T exist
- With PR #37 fixing issue #21, search results now correctly show `total_found` values
- But this doesn't prevent AI hallucination - that's a separate problem

## The Fix

Added explicit warnings and guidelines to `static/instructions.md` to prevent module hallucination:

### 1. Prominent Warning Section at Top
Added a "⚠️ CRITICAL: Module Hallucination Prevention" section at the beginning of instructions with:
- Clear examples of incorrect behavior (hallucinated module)
- Clear examples of correct behavior (using actual module)
- Real-world example showing log-analysis vs observability-instances

### 2. Module Verification Guidelines
Added "CRITICAL: Module Verification" section to code generation guidelines with:
- Explicit workflow: search → verify → use
- Examples of incorrect behavior to avoid
- Step-by-step correct workflow

### 3. Key Principles
- **ALWAYS verify modules exist** before using them
- **NEVER assume** a module exists because a similar one does
- **NEVER infer** module names from patterns
- **Use exact module IDs** from search results

## Testing

All 186 tests pass after the fix:
```bash
.venv/bin/python -m pytest -v
============================= 186 passed in 0.91s ==============================
```

## Example: The Correct Way

### ❌ WRONG (Hallucinated)
```terraform
module "log_analysis" {
  source  = "terraform-ibm-modules/log-analysis/ibm"  # This module doesn't exist!
  version = "1.9.2"
  ...
}
```

### ✅ CORRECT (Verified)
```terraform
module "observability_instances" {
  source  = "terraform-ibm-modules/observability-instances/ibm"  # This module exists!
  version = "3.5.3"
  ...
}
```

## Impact

This fix helps prevent:
- Generating non-functional Terraform code
- User confusion when `terraform init` fails
- Time wasted debugging module source errors
- Loss of trust in the AI's code generation

## Verification

You can verify the module doesn't exist by searching:

```bash
# Search the registry
curl "https://registry.terraform.io/v1/modules/search?q=log%20analysis&limit=10&offset=0" | jq '.modules[] | select(.namespace=="terraform-ibm-modules") | .name'

# Result: "observability-instances" (not "log-analysis")
```

## Next Steps

1. Monitor for similar hallucination patterns with other module types
2. Consider adding runtime validation to catch hallucinated modules
3. Potentially add a "verify module exists" step to code generation workflow
4. Document common module alternatives (e.g., log-analysis → observability-instances)

## Related Issues

- #21 - Total found incorrectly set to 0 (fixed in PR #37)
- #31 - This issue (module hallucination)

## Commit

```
commit 21eeddf
Author: GitHub Copilot
Date: Wed Oct 23 11:38:22 2025

Fix #31: Add module hallucination prevention to instructions
```
