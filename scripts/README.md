# Scripts

This directory contains utility scripts for the TIM MCP server.

## process_whitepaper.py

Downloads and processes the IBM Cloud Terraform Best Practices white paper from source markdown.

### Usage

```bash
uv run python scripts/process_whitepaper.py
```

### Requirements

- `keywords.yml` file at the repository root containing keyword mappings
- Dependencies: `httpx`, `pyyaml`

### Output

The script generates `static/terraform-white-paper.md`, which is served by the MCP resource `file://terraform-whitepaper`.
