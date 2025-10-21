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
from typing import Dict, List, Optional, Tuple, Any, Union

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


# Configuration constants
MODULE_AGE_THRESHOLD_DAYS = 90
OUTPUT_FILENAME = "module_index.json"


def categorize_module(module_name: str, description: str) -> str:
    """
    Categorize a module based on its name and description.
    
    Args:
        module_name: The name of the module
        description: The description of the module
        
    Returns:
        The category name as a string, or "other" if no category matches
    """
    # Handle None values gracefully
    module_name = module_name or ""
    description = description or ""
    
    search_text = f"{module_name} {description}".lower()

    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in search_text for keyword in keywords):
            return category

    return "other"


def clean_excerpt(text: str) -> str:
    """
    Clean up README excerpt by removing unicode symbols and normalizing whitespace.
    
    Args:
        text: The text to clean
        
    Returns:
        The cleaned text with normalized whitespace and removed symbols
    """
    if not text:
        return text

    # Replace common unicode symbols
    replacements = {
        "\u00ae": "",  # ® (registered trademark)
        "\u2122": "",  # ™ (trademark)
        "\u00a9": "",  # © (copyright)
        "\u00a0": " ",  # non-breaking space
        "&reg;": "",
        "&trade;": "",
        "&copy;": ""
    }
    
    for symbol, replacement in replacements.items():
        text = text.replace(symbol, replacement)

    # Normalize whitespace while preserving paragraph breaks
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


def parse_iso_date(date_str: str) -> Optional[datetime]:
    """
    Parse an ISO format date string into a datetime object.
    
    Args:
        date_str: ISO format date string
        
    Returns:
        Datetime object or None if parsing fails
    """
    try:
        # Handle 'Z' timezone designator by replacing with +00:00
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


async def fetch_submodules(
    tf_client: TerraformClient,
    namespace: str,
    name: str,
    provider: str,
    source: str
) -> List[Dict[str, str]]:
    """
    Fetch submodules for a Terraform module.
    
    Args:
        tf_client: TerraformClient instance
        namespace: Module namespace
        name: Module name
        provider: Module provider
        source: Module source URL
        
    Returns:
        List of submodule dictionaries with path, name, and source_url
    """
    submodules = []
    try:
        module_details = await tf_client.get_module_details(
            namespace, name, provider, "latest"
        )

        # Extract submodules
        raw_submodules = module_details.get("submodules", [])
        for submodule in raw_submodules:
            submodule_path = submodule.get("path", "")
            submodule_name = submodule_path.split("/")[-1] if submodule_path else ""

            # Generate GitHub source URL for submodule
            submodule_source_url = (
                f"{source}/tree/main/{submodule_path}"
                if submodule_path
                else source
            )

            submodules.append({
                "path": submodule_path,
                "name": submodule_name,
                "source_url": submodule_source_url,
            })

        # Sort submodules by name
        submodules.sort(key=lambda x: x["name"])

    except Exception as e:
        print(f"Warning: Could not fetch submodules: {e}")

    return submodules


def extract_bullet_items(bullet_text: str, max_length: int = 80) -> List[str]:
    """
    Extract bullet items from a markdown bullet list.
    
    This function parses markdown bullet lists (lines starting with - or *),
    cleans up the items by removing markdown formatting, and returns a list
    of the extracted items.
    
    Args:
        bullet_text: Text containing bullet points
        max_length: Maximum length for each bullet item
        
    Returns:
        List of cleaned bullet items
    """
    items = []
    for line in bullet_text.split("\n"):
        line = line.strip()
        if line.startswith("-") or line.startswith("*"):
            # Remove the bullet marker and leading/trailing whitespace
            item = line.lstrip("-*").strip()
            
            # Remove markdown links but keep the link text
            item = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", item)
            
            # Extract just the first part before colon
            if ":" in item:
                item = item.split(":")[0].strip()
                
            if len(item) > 0 and len(item) < max_length:
                items.append(item)
    
    return items


def should_skip_paragraph(para: str) -> bool:
    """
    Determine if a paragraph should be skipped when extracting README excerpts.
    
    This function checks for common patterns in README files that should be
    skipped when extracting meaningful descriptions, such as code blocks,
    badges, tables, and boilerplate text.
    
    Args:
        para: Paragraph text
        
    Returns:
        True if paragraph should be skipped, False otherwise
    """
    para_lower = para.lower()
    
    # Skip code blocks
    if para.startswith("```"):
        return True
        
    # Skip badges
    if "[![" in para[:50]:
        return True
        
    # Skip markdown tables
    if para.startswith("|") or "|---" in para[:100]:
        return True
        
    # Skip permissions/requirements boilerplate
    skip_phrases = [
        "you need the following permissions",
        "you can report issues",
        "required iam access",
        "## required",
        "uncomment the following",
        "prerequisites",
    ]
    
    if any(skip in para_lower for skip in skip_phrases):
        return True
        
    return False


async def extract_readme_excerpt(gh_client: GitHubClient, source: str) -> str:
    """
    Extract a meaningful excerpt from a module's README.
    
    This function fetches the README.md file from a GitHub repository and
    extracts a meaningful description by:
    1. Looking for paragraphs containing descriptive phrases about the module
    2. Extracting bullet points that describe features
    3. Cleaning up the text by removing markdown formatting and HTML comments
    4. Falling back to the first meaningful paragraph if no descriptive text is found
    
    Args:
        gh_client: GitHubClient instance
        source: Module source URL
        
    Returns:
        Cleaned README excerpt
    """
    readme_excerpt = ""
    try:
        # Parse owner/repo from source URL
        owner_repo = gh_client.parse_github_url(source)
        if not owner_repo:
            return ""
            
        owner, repo = owner_repo
        readme_data = await gh_client.get_file_content(owner, repo, "README.md")
        content = readme_data.get("decoded_content", "")

        # Extract meaningful description paragraph
        # Strategy: Look for descriptive paragraphs, avoiding boilerplate
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]

        # First pass: Look for paragraphs containing descriptive phrases
        for i, para in enumerate(paragraphs):
            if should_skip_paragraph(para):
                continue

            # Check if paragraph contains descriptive phrases (case-insensitive)
            para_lower = para.lower()

            # Remove "## Summary" header if present (keep the content)
            if para.startswith("## Summary"):
                # Remove the header line but keep the rest of the paragraph
                para_lines = para.split("\n", 1)
                if len(para_lines) > 1:
                    para = para_lines[1].strip()
                    para_lower = para.lower()
                else:
                    # Only the header, skip this paragraph
                    continue

            descriptive_phrases = [
                "this module",
                "use this module",
                "this solution",
                "this repository",
                "this root module",
                "terraform module",
                "a module for",
            ]
            
            if any(phrase in para_lower for phrase in descriptive_phrases):
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
                    if ("use real values" in stripped.lower() or
                        "var.<var_name>" in stripped.lower()):
                        continue

                    # Skip standalone URLs
                    if (stripped.startswith("http://") or
                        stripped.startswith("https://")):
                        continue

                    # Check if this is a bullet item
                    if stripped and (stripped.startswith("-") or stripped.startswith("*")):
                        # Extract bullet item text
                        item = stripped.lstrip("-*").strip()
                        # Remove markdown links but keep the link text
                        item = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", item)
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
                    if (readme_excerpt.rstrip().endswith(":") and
                        i + 1 < len(paragraphs)):
                        next_para = paragraphs[i + 1]
                        # Check if next paragraph is a bullet list
                        if (next_para.strip().startswith("-") or
                            next_para.strip().startswith("*")):
                            next_bullet_items = extract_bullet_items(next_para)
                            
                            # Add bullet items as comma-separated list
                            if next_bullet_items:
                                # Limit to first 5 items to keep excerpt reasonable
                                items_to_add = next_bullet_items[:5]
                                readme_excerpt += " " + ", ".join(items_to_add)
                                if len(next_bullet_items) > 5:
                                    readme_excerpt += ", and more"

                    if len(readme_excerpt) > 50:
                        break

        # Second pass: If nothing found, get first meaningful paragraph
        if not readme_excerpt:
            for para in paragraphs:
                if should_skip_paragraph(para) or "<!--" in para:
                    continue
                    
                # Found first real paragraph - use it
                if para and len(para) > 30:
                    readme_excerpt = para
                    break

        # Clean up the excerpt
        readme_excerpt = clean_excerpt(readme_excerpt)

    except Exception as e:
        print(f"Warning: Could not fetch README: {e}")

    return readme_excerpt


async def process_module(
    module: Dict[str, Any],
    tf_client: TerraformClient,
    gh_client: GitHubClient,
    cutoff_date: datetime
) -> Optional[Dict[str, Any]]:
    """
    Process a single module, filtering and enriching with additional data.
    
    This function:
    1. Extracts basic module information (ID, name, description, etc.)
    2. Filters out modules that are too old or from incorrect sources
    3. Categorizes the module based on its name and description
    4. Fetches submodules and README excerpts to enrich the data
    
    Args:
        module: Raw module data from the Terraform registry
        tf_client: TerraformClient instance for API calls
        gh_client: GitHubClient instance for GitHub API calls
        cutoff_date: Date cutoff for filtering modules
        
    Returns:
        Processed module entry or None if module should be filtered out
    """
    module_id = module.get("id", "")
    namespace = module.get("namespace", "")
    name = module.get("name", "")
    provider = module.get("provider", "")
    source = module.get("source", "")
    description = module.get("description", "")
    published_at = module.get("published_at", "")

    # Parse published date
    published_date = parse_iso_date(published_at)
    if published_date and published_date < cutoff_date:
        print(f"Skipping {module_id} - last updated {published_date.date()}")
        return None
    elif not published_date:
        print(f"Warning: Could not parse date for {module_id}: {published_at}")
        # Include module if we can't parse the date (safer default)

    # Validate it's from terraform-ibm-modules GitHub org
    if "github.com/terraform-ibm-modules" not in source:
        print(f"Skipping {module_id} - not from terraform-ibm-modules org")
        return None

    # Categorize module
    category = categorize_module(name, description)

    # Fetch submodules for this module
    print(f"Fetching submodules for {module_id}...")
    submodules = await fetch_submodules(tf_client, namespace, name, provider, source)

    # Fetch README excerpt
    readme_excerpt = await extract_readme_excerpt(gh_client, source)

    # Build module entry with submodules and readme_excerpt
    return {
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


async def generate_module_index():
    """
    Generate the module index JSON file by fetching, filtering, and processing
    Terraform modules from the registry.
    
    This function:
    1. Fetches all modules from the terraform-ibm-modules namespace
    2. Filters out modules older than the threshold (default: 90 days)
    3. Categorizes modules based on name and description
    4. Fetches submodules for each module
    5. Extracts meaningful excerpts from README files
    6. Generates a JSON file with the processed data
    
    The output file is written to the static directory with the name defined
    in OUTPUT_FILENAME.
    """
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
        cutoff_date = datetime.now(UTC) - timedelta(days=MODULE_AGE_THRESHOLD_DAYS)

        # Process modules
        filtered_modules = []
        for module in all_modules:
            processed_module = await process_module(module, tf_client, gh_client, cutoff_date)
            if processed_module:
                filtered_modules.append(processed_module)

        # Sort by downloads (descending)
        filtered_modules.sort(key=lambda x: x["downloads"], reverse=True)

        print(f"\nFiltered to {len(filtered_modules)} modules")

        # Create output structure with metadata
        output = {
            "generated_at": datetime.now(UTC).isoformat(),
            "total_modules": len(filtered_modules),
            "namespace": namespace,
            "filter_criteria": {
                "min_age_days": MODULE_AGE_THRESHOLD_DAYS,
                "required_topics": ["core-team"],
                "exclude_archived": True,
            },
            "modules": filtered_modules,
        }

        # Write to static directory
        output_path = Path(__file__).parent.parent / "static" / OUTPUT_FILENAME
        output_path.parent.mkdir(exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(output, f, indent=2)

        print(f"\n✅ Module index generated: {output_path}")
        print(f"   Total modules: {len(filtered_modules)}")
        print(f"   Categories: {len({m['category'] for m in filtered_modules})}")


if __name__ == "__main__":
    asyncio.run(generate_module_index())
