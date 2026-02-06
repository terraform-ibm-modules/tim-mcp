"""Test for the get_terraform_whitepaper tool."""

from pathlib import Path

# Import the specific tool function from server, not the decorator
from tim_mcp.server import _load_instructions


def test_whitepaper_file_exists():
    """Test that the whitepaper markdown file exists."""
    # Check development path (now in test/integration, need to go up two more levels)
    dev_path = (
        Path(__file__).parent.parent.parent / "static" / "terraform-white-paper.md"
    )
    assert dev_path.exists(), f"Whitepaper file not found at {dev_path}"

    # Check that it's readable and has content
    content = dev_path.read_text(encoding="utf-8")
    assert len(content) > 0, "Whitepaper file is empty"
    assert "IBM Cloud Terraform Best Practices" in content, (
        "Whitepaper content doesn't contain expected title"
    )


def test_whitepaper_markdown_format():
    """Test that the whitepaper content is properly formatted markdown."""
    dev_path = (
        Path(__file__).parent.parent.parent / "static" / "terraform-white-paper.md"
    )
    content = dev_path.read_text(encoding="utf-8")

    # Check for basic markdown structure
    assert content.startswith("# "), "Whitepaper should start with a main heading"

    # Check for expected content
    assert "Terraform" in content, "Whitepaper should mention Terraform"
    assert "IBM Cloud" in content, "Whitepaper should mention IBM Cloud"
    assert "Best Practices" in content, "Whitepaper should mention best practices"


def test_instructions_still_load():
    """Test that the original instructions still load correctly after our changes."""
    instructions = _load_instructions()
    assert isinstance(instructions, str)
    assert len(instructions) > 0
    assert "TIM" in instructions or "Terraform" in instructions
