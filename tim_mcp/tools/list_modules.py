"""
List modules tool implementation for TIM-MCP.

This module provides functionality to list all terraform-ibm-modules with
categorization for better context enrichment.
"""

from datetime import datetime

from ..clients.github_client import GitHubClient
from ..clients.terraform_client import TerraformClient
from ..config import Config
from ..exceptions import TIMError
from ..types import ModuleListItem, ModuleListResponse

# Required topics that must be present in the GitHub repository
REQUIRED_TOPICS = ["core-team"]

# Category mappings based on module names and keywords
CATEGORY_KEYWORDS = {
    "networking": [
        "vpc",
        "network",
        "subnet",
        "gateway",
        "load-balancer",
        "lb",
        "dns",
        "transit",
        "vpn",
        "direct-link",
        "cdn",
        "firewall",
    ],
    "security": [
        "security",
        "secrets-manager",
        "key-protect",
        "scc",
        "compliance",
        "iam",
        "access",
        "certificate",
        "encryption",
        "firewall",
        "cbr",
        "context-based-restrictions",
    ],
    "compute": [
        "vsi",
        "instance",
        "compute",
        "server",
        "vm",
        "virtual-server",
        "bare-metal",
        "power",
        "code-engine",
        "batch",
    ],
    "containers": [
        "kubernetes",
        "iks",
        "openshift",
        "container",
        "cluster",
        "k8s",
        "workload",
        "registry",
    ],
    "storage": [
        "storage",
        "cos",
        "object-storage",
        "block-storage",
        "file-storage",
        "backup",
        "volume",
    ],
    "database": [
        "database",
        "db",
        "postgres",
        "mysql",
        "mongodb",
        "redis",
        "cloudant",
        "etcd",
        "elasticsearch",
        "icd",
        "databases",
    ],
    "observability": [
        "observability",
        "monitoring",
        "logging",
        "sysdig",
        "logdna",
        "log-analysis",
        "cloud-logs",
        "metrics",
        "activity-tracker",
        "atracker",
        "event-notifications",
    ],
    "devops": [
        "devops",
        "ci-cd",
        "toolchain",
        "pipeline",
        "schematics",
        "project",
        "projects",
    ],
    "integration": [
        "event-streams",
        "kafka",
        "mq",
        "message",
        "api",
        "app-config",
        "appid",
    ],
    "ai-ml": [
        "watson",
        "ai",
        "ml",
        "machine-learning",
        "watsonx",
        "studio",
    ],
    "management": [
        "resource-group",
        "account",
        "tagging",
        "catalog",
        "enterprise",
    ],
}


def _categorize_module(name: str, description: str) -> str:
    """
    Categorize a module based on its name and description.

    Args:
        name: Module name
        description: Module description

    Returns:
        Category string
    """
    # Combine name and description for matching
    text_to_match = f"{name} {description}".lower()

    # Check each category's keywords
    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text_to_match:
                return category

    # Default category
    return "other"


async def list_modules_impl(config: Config) -> ModuleListResponse:
    """
    Implementation function for the list_modules MCP tool.

    This function fetches all modules from the terraform-ibm-modules namespace,
    validates them against GitHub repository criteria, categorizes them, and
    returns them sorted by download count.

    Args:
        config: Configuration instance for client setup and behavior

    Returns:
        ModuleListResponse containing all validated modules with categorization

    Raises:
        TerraformRegistryError: When the Terraform Registry API fails
        RateLimitError: When API rate limits are exceeded
        TIMError: For other errors during processing
    """
    from ..logging import get_logger

    logger = get_logger(__name__)

    # Use the configured namespace
    namespace = config.allowed_namespaces[0] if config.allowed_namespaces else "terraform-ibm-modules"

    logger.info(f"Fetching all modules from namespace: {namespace}")

    # Create and use both Terraform and GitHub clients as async context managers
    async with (
        TerraformClient(config) as terraform_client,
        GitHubClient(config) as github_client,
    ):
        try:
            # Fetch all modules from the namespace
            all_modules_data = await terraform_client.list_all_modules(namespace)

            logger.info(
                f"Fetched {len(all_modules_data)} modules from Terraform Registry"
            )

            # Process and validate each module
            validated_modules = []

            for module_data in all_modules_data:
                try:
                    # Extract basic module info
                    module_id = module_data.get("id", "")
                    name = module_data.get("name", "")
                    description = module_data.get("description", "")
                    source_url = module_data.get("source", "")
                    downloads = module_data.get("downloads", 0)
                    version = module_data.get("version", "")
                    published_at_str = module_data.get("published_at", "")

                    # Skip if missing required fields
                    if not all([module_id, name, source_url]):
                        logger.warning(
                            f"Skipping module with missing required fields: {module_id}"
                        )
                        continue

                    # Apply module exclusion filtering
                    if module_id in config.excluded_modules:
                        logger.info("Module excluded from results", module_id=module_id)
                        continue

                    # Parse published_at
                    try:
                        if published_at_str.endswith("Z"):
                            published_at_str = published_at_str[:-1] + "+00:00"
                        published_at = datetime.fromisoformat(published_at_str)
                    except (ValueError, TypeError):
                        published_at = datetime.now()

                    # Validate repository (not archived, has required topics)
                    repo_info = github_client.parse_github_url(source_url)
                    if not repo_info:
                        logger.warning(
                            f"Could not parse GitHub URL for module: {module_id}"
                        )
                        continue

                    owner, repo_name = repo_info

                    # Get repository information
                    repo_data = await github_client.get_repository_info(owner, repo_name)

                    # Check if repository is archived
                    if repo_data.get("archived", False):
                        logger.info(
                            f"Repository {owner}/{repo_name} is archived, excluding module {module_id}"
                        )
                        continue

                    # Check if repository has all required topics
                    repo_topics = repo_data.get("topics", [])
                    missing_topics = [
                        topic for topic in REQUIRED_TOPICS if topic not in repo_topics
                    ]

                    if missing_topics:
                        logger.info(
                            f"Repository {owner}/{repo_name} missing required topics {missing_topics}, excluding module {module_id}"
                        )
                        continue

                    # Categorize the module
                    category = _categorize_module(name, description)

                    # Create ModuleListItem
                    module_item = ModuleListItem(
                        module_id=module_id,
                        name=name,
                        description=description,
                        category=category,
                        latest_version=version,
                        downloads=downloads if isinstance(downloads, int) else 0,
                        source_url=source_url,
                        published_at=published_at,
                    )

                    validated_modules.append(module_item)

                except Exception as e:
                    logger.warning(
                        f"Error processing module {module_data.get('id', 'unknown')}: {e}"
                    )
                    continue

            # Sort by downloads in descending order
            validated_modules.sort(key=lambda m: m.downloads, reverse=True)

            logger.info(
                f"Successfully processed {len(validated_modules)} validated modules"
            )

            # Create and return the response
            return ModuleListResponse(
                total_count=len(validated_modules),
                modules=validated_modules,
            )

        except TIMError:
            # Re-raise TIM errors as-is
            raise
        except Exception as e:
            logger.exception(f"Unexpected error in list_modules: {e}")
            raise TIMError(f"Unexpected error listing modules: {e}") from e
