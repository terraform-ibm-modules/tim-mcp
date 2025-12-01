"""
MCP Prompts for TIM-MCP Server.

This module loads Strands Agent SOPs (Standard Operating Procedures) as MCP prompts.
SOPs are structured markdown workflows with RFC 2119 constraints that guide AI agents
through repeatable, reliable processes.
"""

from pathlib import Path
from mcp.server.fastmcp.prompts.base import Message


def _find_sop_file(filename: str) -> Path:
    """
    Find a SOP file in the sops directory, checking both packaged and development locations.

    Args:
        filename: Name of the SOP file to find

    Returns:
        Path object to the found file

    Raises:
        FileNotFoundError: If the file cannot be found in either location
    """
    # First try the packaged location (when installed via pip/uvx)
    packaged_path = Path(__file__).parent / "sops" / filename
    # Then try the development location (when running from source)
    dev_path = Path(__file__).parent.parent / "sops" / filename

    if packaged_path.exists():
        return packaged_path
    elif dev_path.exists():
        return dev_path
    else:
        raise FileNotFoundError(
            f"SOP file '{filename}' not found in packaged location ({packaged_path}) "
            f"or development location ({dev_path})"
        )


def _load_sop(filename: str, **params) -> str:
    """
    Load a SOP markdown file and inject parameters.

    Args:
        filename: Name of the SOP file to load
        **params: Parameters to inject into the SOP

    Returns:
        SOP content with parameters injected
    """
    sop_path = _find_sop_file(filename)
    content = sop_path.read_text(encoding="utf-8")

    # Inject parameters into the SOP
    for key, value in params.items():
        placeholder = f"{{{key}}}"
        content = content.replace(placeholder, str(value))

    return content


def register_prompts(mcp):
    """
    Register all Agent SOPs as MCP prompts.

    Args:
        mcp: FastMCP server instance
    """

    @mcp.prompt()
    def quick_start(goal: str, has_existing_example: str = "unknown") -> list[Message]:
        """
        Universal entry point for TIM-MCP workflows.

        This SOP helps route you to the appropriate workflow based on your goal.
        Use this when you're not sure which workflow to follow or want guidance on
        getting started with Terraform IBM Modules.

        Args:
            goal: What you want to accomplish (e.g., "deploy a VPC", "create infrastructure")
            has_existing_example: Whether you want to use an existing example ("yes", "no", or "unknown")

        Returns:
            Agent SOP that guides workflow selection
        """
        # Load and parameterize the SOP
        sop_content = _load_sop(
            "quick-start.md",
            goal=goal,
            has_existing_example=has_existing_example
        )

        return [
            Message(
                role="user",
                content=f"Follow this SOP to help me get started:\n\n{sop_content}"
            )
        ]

    @mcp.prompt()
    def examples_workflow(use_case: str, complexity: str = "basic") -> list[Message]:
        """
        Step-by-step workflow for finding and using module examples.

        This SOP guides you through the Examples/Samples workflow for discovering
        and using existing Terraform module examples from the TIM ecosystem.

        Args:
            use_case: What you want to deploy (e.g., "VPC", "Kubernetes cluster", "database")
            complexity: Example complexity level - "basic", "complete", or "solution" (default: "basic")

        Returns:
            Agent SOP that guides the examples workflow
        """
        # Normalize complexity
        if complexity not in ["basic", "complete", "solution"]:
            complexity = "basic"

        # Load and parameterize the SOP
        sop_content = _load_sop(
            "examples-workflow.md",
            use_case=use_case,
            complexity=complexity
        )

        return [
            Message(
                role="user",
                content=f"Follow this SOP to find and use examples:\n\n{sop_content}"
            )
        ]

    @mcp.prompt()
    def development_workflow(requirement: str,
                            documentation_dir: str = ".sop/planning",
                            repo_root: str = ".") -> list[Message]:
        """
        Step-by-step workflow for developing custom Terraform configurations.

        This SOP guides you through the New Development workflow for building
        custom Terraform configurations using Terraform IBM Modules.

        Args:
            requirement: What you need to build (e.g., "custom VPC with 3 subnets")
            documentation_dir: Directory for planning documents (default: ".sop/planning")
            repo_root: Root directory of the repository (default: ".")

        Returns:
            Agent SOP that guides the development workflow
        """
        # Load and parameterize the SOP
        sop_content = _load_sop(
            "development-workflow.md",
            requirement=requirement,
            documentation_dir=documentation_dir,
            repo_root=repo_root
        )

        return [
            Message(
                role="user",
                content=f"Follow this SOP to build custom infrastructure:\n\n{sop_content}"
            )
        ]
