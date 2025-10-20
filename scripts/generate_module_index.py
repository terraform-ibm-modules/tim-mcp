#!/usr/bin/env python3
"""
Generate static module index for TIM-MCP.

This script fetches all IBM Terraform modules, filters them, categorizes them,
and generates a static JSON file that can be indexed by LLMs.

Run this script at build time to update the module index.
"""

import asyncio
import json
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from tim_mcp.clients.github_client import GitHubClient
from tim_mcp.clients.terraform_client import TerraformClient
from tim_mcp.config import load_config
from tim_mcp.utils.cache import Cache

# Category mappings (same as in list_modules.py)
# NOTE: Categories are checked in order, so more specific categories should come first
CATEGORY_KEYWORDS = {
    "ai-ml": ["watsonx-", "watson-", "machine-learning", "ml-", "data-science"],
    "database": [
        "icd-mongodb",
        "icd-postgresql",
        "icd-redis",
        "icd-mysql",
        "icd-elasticsearch",
        "icd-rabbitmq",
        "cloudant",
        "icd",
        "database",
        "postgres",
        "mysql",
        "mongodb",
        "redis",
        "elasticsearch",
        "rabbitmq",
    ],
    "observability": [
        "cloud-logs",
        "cloud-monitoring",
        "monitoring-agent",
        "logs-agent",
        "event-notifications",
        "observability",
        "activity-tracker",
        "sysdig",
        "logdna",
        "metrics",
        "notifications",
    ],
    "management": [
        "app-configuration",
        "catalog-management",
        "resource-group",
        "account-infrastructure",
        "enterprise",
        "project",
        "catalog",
    ],
    "security": [
        "secrets-manager",
        "secrets",
        "kms",
        "key-protect",
        "hpcs",
        "crypto",
        "cbr",
        "context-based-restrictions",
        "iam",
        "appid",
        "authentication",
        "authorization",
        "scc",
        "workload-protection",
        "external-secrets-operator",
    ],
    "containers": [
        "kubernetes",
        "iks",
        "openshift",
        "container-registry",
        "code-engine",
        "cluster",
        "serverless",
    ],
    "networking": [
        "security-group",
        "vpc",
        "subnet",
        "vpe-gateway",
        "private-path",
        "load-balancer",
        "alb",
        "nlb",
        "dns",
        "transit-gateway",
        "cis",
        "internet-services",
        "vpn",
        "site-to-site",
    ],
    "storage": ["cos", "object-storage", "storage", "volume", "block"],
    "compute": [
        "dedicated-host",
        "bare-metal",
        "powervs",
        "instance",
        "virtual-server",
        "vsi",
        "server",
    ],
    "integration": ["event-streams", "mq", "app-connect", "integration", "messaging"],
    "devops": ["toolchain", "pipeline", "ci-cd", "devops", "schematics"],
}


def categorize_module(module_name: str, description: str) -> str:
    """Categorize a module based on its name and description."""
    search_text = f"{module_name} {description}".lower()

    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in search_text for keyword in keywords):
            return category

    return "other"


def clean_excerpt(text: str) -> str:
    """Clean up README excerpt by removing unicode symbols and normalizing whitespace."""
    if not text:
        return text

    # Replace common unicode symbols
    text = text.replace("\u00ae", "")  # ® (registered trademark)
    text = text.replace("\u2122", "")  # ™ (trademark)
    text = text.replace("\u00a9", "")  # © (copyright)
    text = text.replace("\u00a0", " ")  # non-breaking space
    text = text.replace("&reg;", "")
    text = text.replace("&trade;", "")
    text = text.replace("&copy;", "")

    # Normalize whitespace - replace multiple spaces/newlines with single space
    # But preserve intentional paragraph breaks (double newline)
    import re

    # First preserve double newlines as a placeholder
    text = text.replace("\n\n", "<<<PARAGRAPH>>>")
    # Remove other newlines and tabs
    text = text.replace("\n", " ").replace("\t", " ")
    # Restore paragraph breaks
    text = text.replace("<<<PARAGRAPH>>>", "\n\n")
    # Collapse multiple spaces
    text = re.sub(r" +", " ", text)
    # Clean up spaces around paragraph breaks
    text = re.sub(r" *\n\n *", "\n\n", text)

    return text.strip()


async def generate_module_index():
    """Generate the module index JSON file."""
    print("Starting module index generation...")

    # Initialize clients
    config = load_config()
    cache = Cache(ttl=0)  # Disable cache for fresh data

    async with (
        TerraformClient(config, cache) as tf_client,
        GitHubClient(config, cache) as gh_client,
    ):
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

            # Fetch README excerpt
            readme_excerpt = ""
            try:
                # Parse owner/repo from source URL
                owner_repo = gh_client.parse_github_url(source)
                if owner_repo:
                    owner, repo = owner_repo
                    readme_data = await gh_client.get_file_content(
                        owner, repo, "README.md"
                    )
                    content = readme_data.get("decoded_content", "")

                    # Extract meaningful description paragraph
                    # Strategy: Look for descriptive paragraphs, avoiding boilerplate
                    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]

                    # First pass: Look for paragraphs containing descriptive phrases
                    for i, para in enumerate(paragraphs):
                        # Skip code blocks
                        if para.startswith("```"):
                            continue
                        # Skip badges
                        if "[![" in para[:50]:
                            continue
                        # Skip markdown tables
                        if para.startswith("|") or "|---" in para[:100]:
                            continue

                        # Check if paragraph contains descriptive phrases (case-insensitive)
                        para_lower = para.lower()

                        # Skip permissions/requirements boilerplate
                        if any(
                            skip in para_lower
                            for skip in [
                                "you need the following permissions",
                                "you can report issues",
                                "required iam access",
                                "## required",
                                "uncomment the following",
                            ]
                        ):
                            continue

                        # Special handling for "## Summary" sections
                        if para.startswith("## Summary"):
                            # The description is likely in the next paragraph
                            continue

                        if any(
                            phrase in para_lower
                            for phrase in [
                                "this module",
                                "use this module",
                                "this solution",
                                "this root module",
                                "terraform module",
                                "a module for",
                            ]
                        ):
                            # Extract the descriptive text, removing HTML comments and headers
                            lines = para.split("\n")
                            description_lines = []
                            bullet_items = []
                            in_html_comment = False
                            intro_text = ""

                            for line in lines:
                                stripped = line.strip()

                                # Track HTML comment state
                                if "<!--" in stripped:
                                    in_html_comment = True
                                if "-->" in stripped:
                                    in_html_comment = False
                                    continue  # Skip the closing comment line

                                # Skip if we're inside a comment
                                if in_html_comment:
                                    continue

                                # Skip section headers
                                if stripped.startswith("#"):
                                    continue

                                # Skip documentation meta-lines (only if they start the line)
                                if stripped.lower().startswith("for information, see"):
                                    continue

                                # Skip placeholder/template text
                                if (
                                    "use real values" in stripped.lower()
                                    or "var.<var_name>" in stripped.lower()
                                ):
                                    continue

                                # Skip standalone URLs
                                if stripped.startswith(
                                    "http://"
                                ) or stripped.startswith("https://"):
                                    continue

                                # Check if this is a bullet item
                                if stripped and (
                                    stripped.startswith("-") or stripped.startswith("*")
                                ):
                                    # Extract bullet item text
                                    item = stripped.lstrip("-*").strip()
                                    # Remove markdown links but keep the link text
                                    item = re.sub(
                                        r"\[([^\]]+)\]\([^\)]+\)", r"\1", item
                                    )
                                    # Extract just the first part before colon
                                    if ":" in item:
                                        item = item.split(":")[0].strip()
                                    if len(item) > 0 and len(item) < 80:
                                        bullet_items.append(item)
                                elif stripped:
                                    # This is intro text before bullets
                                    if not intro_text:
                                        intro_text = stripped
                                    else:
                                        description_lines.append(stripped)

                            # Build the excerpt
                            if intro_text or description_lines:
                                # Start with intro text if we have it
                                if intro_text:
                                    readme_excerpt = intro_text
                                    # If we have bullet items from this paragraph, add them
                                    if bullet_items:
                                        items_to_add = bullet_items[:5]
                                        readme_excerpt += " " + ", ".join(items_to_add)
                                        if len(bullet_items) > 5:
                                            readme_excerpt += ", and more"
                                else:
                                    readme_excerpt = "\n".join(description_lines)

                                # Also check if the next paragraph is a bullet list
                                # If the excerpt ends with ":" and next para has bullets, append them
                                if readme_excerpt.rstrip().endswith(
                                    ":"
                                ) and i + 1 < len(paragraphs):
                                    next_para = paragraphs[i + 1]
                                    # Check if next paragraph is a bullet list
                                    if next_para.strip().startswith(
                                        "-"
                                    ) or next_para.strip().startswith("*"):
                                        next_bullet_items = []
                                        for bullet_line in next_para.split("\n"):
                                            bullet_line = bullet_line.strip()
                                            if bullet_line.startswith(
                                                "-"
                                            ) or bullet_line.startswith("*"):
                                                # Remove the bullet marker and leading/trailing whitespace
                                                item = bullet_line.lstrip("-*").strip()

                                                # Remove markdown links but keep the link text
                                                # Pattern: [text](url) -> text
                                                item = re.sub(
                                                    r"\[([^\]]+)\]\([^\)]+\)",
                                                    r"\1",
                                                    item,
                                                )

                                                # Extract just the first sentence/clause before colon or period
                                                if ":" in item:
                                                    item = item.split(":")[0].strip()
                                                # Limit length to avoid overly long descriptions
                                                if len(item) > 0 and len(item) < 80:
                                                    next_bullet_items.append(item)

                                        # Add bullet items as comma-separated list
                                        if next_bullet_items:
                                            # Limit to first 5 items to keep excerpt reasonable
                                            items_to_add = next_bullet_items[:5]
                                            readme_excerpt += " " + ", ".join(
                                                items_to_add
                                            )
                                            if len(next_bullet_items) > 5:
                                                readme_excerpt += ", and more"

                                if len(readme_excerpt) > 50:
                                    break

                    # Second pass: If nothing found, get first meaningful paragraph
                    if not readme_excerpt:
                        for para in paragraphs:
                            # Skip code blocks
                            if para.startswith("```"):
                                continue
                            # Skip markdown headers
                            if para.startswith("#"):
                                continue
                            # Skip badges and HTML comments (anywhere in paragraph)
                            if "[![" in para or "<!--" in para:
                                continue
                            # Skip markdown tables
                            if para.startswith("|") or "|---" in para[:100]:
                                continue
                            # Skip permissions/requirements/support
                            if any(
                                skip in para.lower()
                                for skip in [
                                    "you need the following permissions",
                                    "you can report issues",
                                    "required iam access",
                                    "prerequisites",
                                    "uncomment the following",
                                ]
                            ):
                                continue
                            # Found first real paragraph - use it
                            if para and len(para) > 30:
                                readme_excerpt = para
                                break

                    # Clean up the excerpt
                    readme_excerpt = clean_excerpt(readme_excerpt)

            except Exception as e:
                print(f"Warning: Could not fetch README for {module_id}: {e}")

            # Build module entry with submodules and readme_excerpt
            module_entry = {
                "id": module_id,
                "name": name,
                "description": description,
                "category": category,
                "downloads": module.get("downloads", 0),
                "published_at": published_at,
                "source_url": source,
                "submodules": submodules,
                "readme_excerpt": readme_excerpt,
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
