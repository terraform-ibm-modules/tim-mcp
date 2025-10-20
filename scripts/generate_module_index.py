#!/usr/bin/env python3
"""
Generate static module index for TIM-MCP.

This script fetches all IBM Terraform modules, filters them, categorizes them,
and generates a static JSON file that can be indexed by LLMs.

Run this script at build time to update the module index.
"""

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from tim_mcp.clients.terraform_client import TerraformClient
from tim_mcp.config import load_config
from tim_mcp.utils.cache import Cache

# Category mappings (same as in list_modules.py)
CATEGORY_KEYWORDS = {
    "networking": [
        "vpc",
        "subnet",
        "network",
        "load-balancer",
        "alb",
        "nlb",
        "dns",
        "transit",
    ],
    "security": [
        "security",
        "secrets",
        "kms",
        "key-protect",
        "cbr",
        "context-based-restrictions",
        "iam",
        "access",
    ],
    "compute": ["instance", "virtual-server", "vsi", "bare-metal", "server"],
    "containers": ["kubernetes", "iks", "openshift", "container", "cluster"],
    "storage": ["cos", "object-storage", "storage", "volume", "block"],
    "database": ["database", "postgres", "mysql", "mongodb", "redis", "icd"],
    "observability": [
        "observability",
        "monitoring",
        "logging",
        "activity-tracker",
        "sysdig",
        "logdna",
        "metrics",
    ],
    "devops": ["toolchain", "pipeline", "ci-cd", "devops", "schematics"],
    "integration": ["event-streams", "mq", "app-connect", "integration", "messaging"],
    "ai-ml": ["watson", "ai", "machine-learning", "ml", "data-science"],
    "management": ["resource-group", "account", "enterprise", "project", "management"],
}


def categorize_module(module_name: str, description: str) -> str:
    """Categorize a module based on its name and description."""
    search_text = f"{module_name} {description}".lower()

    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in search_text for keyword in keywords):
            return category

    return "other"


async def generate_module_index():
    """Generate the module index JSON file."""
    print("Starting module index generation...")

    # Initialize clients
    config = load_config()
    cache = Cache(ttl=0)  # Disable cache for fresh data

    async with TerraformClient(config, cache) as tf_client:
        # Fetch all modules from terraform-ibm-modules namespace
        namespace = config.allowed_namespaces[0]  # Use first allowed namespace
        print(f"Fetching modules from namespace: {namespace}")
        all_modules = await tf_client.list_all_modules(namespace)
        print(f"Found {len(all_modules)} total modules")

        # Calculate cutoff date (3 months ago)
        three_months_ago = datetime.now(UTC) - timedelta(days=90)

        # Process modules
        filtered_modules = []
        for module in all_modules:
            module_id = module.get("id", "")
            namespace = module.get("namespace", "")
            name = module.get("name", "")
            provider = module.get("provider", "")

            # Parse published date
            published_at = module.get("published_at", "")
            try:
                published_date = datetime.fromisoformat(
                    published_at.replace("Z", "+00:00")
                )

                # Filter: skip modules older than 3 months
                if published_date < three_months_ago:
                    print(
                        f"Skipping {module_id} - last updated {published_date.date()}"
                    )
                    continue
            except (ValueError, AttributeError):
                print(f"Warning: Could not parse date for {module_id}: {published_at}")
                # Include module if we can't parse the date (safer default)

            source = module.get("source", "")

            # Validate it's from terraform-ibm-modules GitHub org
            if "github.com/terraform-ibm-modules" not in source:
                print(f"Skipping {module_id} - not from terraform-ibm-modules org")
                continue

            # Categorize module
            description = module.get("description", "")
            category = categorize_module(name, description)

            # Fetch submodules for this module
            print(f"Fetching submodules for {module_id}...")
            submodules = []
            try:
                module_details = await tf_client.get_module_details(
                    namespace, name, provider, "latest"
                )

                # Extract submodules
                raw_submodules = module_details.get("submodules", [])
                for submodule in raw_submodules:
                    submodule_path = submodule.get("path", "")
                    submodule_name = (
                        submodule_path.split("/")[-1] if submodule_path else ""
                    )

                    # Generate GitHub source URL for submodule
                    submodule_source_url = (
                        f"{source}/tree/main/{submodule_path}"
                        if submodule_path
                        else source
                    )

                    submodules.append(
                        {
                            "path": submodule_path,
                            "name": submodule_name,
                            "source_url": submodule_source_url,
                        }
                    )

                # Sort submodules by name
                submodules.sort(key=lambda x: x["name"])

            except Exception as e:
                print(f"Warning: Could not fetch submodules for {module_id}: {e}")

            # Build module entry with submodules
            module_entry = {
                "id": module_id,
                "name": name,
                "description": description,
                "category": category,
                "downloads": module.get("downloads", 0),
                "published_at": published_at,
                "source_url": source,
                "submodules": submodules,
            }

            filtered_modules.append(module_entry)

        # Sort by downloads (descending)
        filtered_modules.sort(key=lambda x: x["downloads"], reverse=True)

        print(f"\nFiltered to {len(filtered_modules)} modules")

        # Create output structure
        output = {
            "generated_at": datetime.now(UTC).isoformat(),
            "total_modules": len(filtered_modules),
            "namespace": namespace,
            "filter_criteria": {
                "min_age_days": 90,
                "required_topics": ["core-team"],
                "exclude_archived": True,
            },
            "modules": filtered_modules,
        }

        # Write to static directory
        output_path = Path(__file__).parent.parent / "static" / "module_index.json"
        output_path.parent.mkdir(exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(output, f, indent=2)

        print(f"\n✅ Module index generated: {output_path}")
        print(f"   Total modules: {len(filtered_modules)}")
        print(f"   Categories: {len({m['category'] for m in filtered_modules})}")


if __name__ == "__main__":
    asyncio.run(generate_module_index())
