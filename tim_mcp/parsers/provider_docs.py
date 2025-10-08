"""
Parser for Terraform provider documentation markdown.

This module extracts structured information from provider documentation
including arguments, attributes, and examples.
"""

import re
from typing import Any

from ..types import (
    ProviderResourceArgument,
    ProviderResourceAttribute,
    ProviderResourceExample,
    RelatedResource,
)


def extract_description(markdown: str) -> str:
    """
    Extract the main description from markdown.

    Args:
        markdown: Provider documentation markdown

    Returns:
        Description text
    """
    # Look for description in frontmatter
    frontmatter_match = re.search(
        r"description:\s*\|-?\s*\n\s*([^\n]+)", markdown, re.MULTILINE
    )
    if frontmatter_match:
        return frontmatter_match.group(1).strip()

    # Look for first paragraph after title
    lines = markdown.split("\n")
    in_content = False
    description_lines = []

    for line in lines:
        # Skip frontmatter
        if line.strip() == "---":
            in_content = not in_content
            continue

        if in_content:
            # Skip title lines
            if line.startswith("#"):
                continue

            # First non-empty line after title
            if line.strip():
                description_lines.append(line.strip())
                # Get first sentence or line
                if "." in line:
                    break

    if description_lines:
        desc = " ".join(description_lines)
        # Get first sentence
        match = re.match(r"([^.!?]+[.!?])", desc)
        if match:
            return match.group(1).strip()
        return desc[:200]  # Truncate if no sentence ending

    return "No description available"


def extract_default_value(full_text: str) -> Any | None:
    """
    Extract default value from various format patterns.

    Args:
        full_text: Full argument text including continuation lines

    Returns:
        Default value as string or None
    """
    # Pattern 1: "The default value is `VALUE`" (highest priority)
    match = re.search(r"[Tt]he default value is `([^`]+)`", full_text)
    if match:
        return match.group(1)

    # Pattern 2: "default is `VALUE`" (lowercase, often at end)
    match = re.search(r"default is `([^`]+)`", full_text, re.IGNORECASE)
    if match:
        return match.group(1)

    # Pattern 3: "Default: `VALUE`" or "Defaults to `VALUE`"
    match = re.search(r"[Dd]efault[s]?\s*(?:to|:)\s*`([^`]+)`", full_text)
    if match:
        return match.group(1)

    # Pattern 4: "(default: VALUE)" without backticks
    match = re.search(r"\(default:\s*([^)]+)\)", full_text, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # Pattern 5: Boolean implicit defaults
    if re.search(r"is (disabled|false) by default", full_text, re.IGNORECASE):
        return "false"
    if re.search(r"is (enabled|true) by default", full_text, re.IGNORECASE):
        return "true"

    # Pattern 6: "This is the default" after value
    match = re.search(r"`([^`]+)`[^`]*[Tt]his is the default", full_text)
    if match:
        return match.group(1)

    return None


def extract_arguments(markdown: str) -> list[ProviderResourceArgument]:
    """
    Extract argument definitions from markdown with comprehensive format support.

    Args:
        markdown: Provider documentation markdown

    Returns:
        List of argument definitions
    """
    arguments = []

    # Find the "Argument Reference" section (case insensitive)
    arg_section_pattern = r"##\s+Argument [Rr]eference\s*\n(.*?)(?=##|$)"
    arg_section_match = re.search(
        arg_section_pattern, markdown, re.DOTALL | re.IGNORECASE
    )

    if not arg_section_match:
        return arguments

    arg_section = arg_section_match.group(1)

    # Pattern captures: bullet type, name, metadata, full text (including continuation lines)
    # Continuation lines: any line NOT starting with a new bullet ([-*] `)
    arg_pattern = (
        r"([-*])\s+`([^`]+)`\s*-\s*\((.*?)\)\s+([^\n]+(?:\n(?![-*]\s+`)[^\n]*)*)"
    )

    for match in re.finditer(arg_pattern, arg_section):
        name = match.group(2).strip()
        metadata = match.group(3).strip()
        full_text = match.group(4).strip()

        # Extract first line as main description
        lines = full_text.split("\n")
        description = lines[0].strip()

        # Parse required/optional from metadata
        required = "required" in metadata.lower()

        # Extract type with support for compound types
        type_match = re.search(
            r"(String|Integer|Boolean|Bool|List|Map|Number|Float|Object|Array)(?:\s+of\s+([A-Z]\w+))?",
            metadata,
            re.IGNORECASE,
        )
        if type_match:
            base_type = type_match.group(1).title()
            sub_type = type_match.group(2)
            arg_type = f"{base_type} of {sub_type.title()}" if sub_type else base_type
        else:
            arg_type = "String"

        # Extract default value using multiple strategies
        default_value = extract_default_value(full_text)

        arguments.append(
            ProviderResourceArgument(
                name=name,
                type=arg_type,
                required=required,
                description=description,
                default=default_value,
            )
        )

    return arguments


def extract_attributes(markdown: str) -> list[ProviderResourceAttribute]:
    """
    Extract attribute definitions from markdown.

    Args:
        markdown: Provider documentation markdown

    Returns:
        List of attribute definitions
    """
    attributes = []

    # Find the "Attribute Reference" or "Attributes Reference" section
    attr_section_pattern = r"##\s+Attributes?\s+Reference\s*\n(.*?)(?=##|$)"
    attr_section_match = re.search(
        attr_section_pattern, markdown, re.DOTALL | re.IGNORECASE
    )

    if not attr_section_match:
        return attributes

    attr_section = attr_section_match.group(1)

    # Pattern for attribute entries (bullet points with * or -)
    # Matches: - `name` - (Type) Description or - `name` - Description
    attr_pattern = r"[-*]\s+`([^`]+)`\s*-\s*(?:\(([^)]+)\))?\s*([^\n]+)"

    for match in re.finditer(attr_pattern, attr_section):
        name = match.group(1).strip()
        type_info = match.group(2)  # May be None
        description = match.group(3).strip()

        # Extract type from the (Type) group or infer from name/description
        if type_info:
            # Type was explicitly provided in (Type) format
            attr_type = type_info.strip().title()
        else:
            # Infer type from name/description as fallback
            attr_type = "String"  # default
            if "id" in name.lower() or "crn" in name.lower():
                attr_type = "String"
            elif "count" in name.lower() or "number" in name.lower():
                attr_type = "Number"
            elif "list" in description.lower():
                attr_type = "List"
            elif "bool" in description.lower() or name.lower().startswith("is_"):
                attr_type = "Bool"

        attributes.append(
            ProviderResourceAttribute(
                name=name,
                type=attr_type,
                description=description,
            )
        )

    return attributes


def extract_examples(markdown: str) -> list[ProviderResourceExample]:
    """
    Extract code examples from markdown.

    Args:
        markdown: Provider documentation markdown

    Returns:
        List of examples with titles and code
    """
    examples = []

    # Find all code blocks with optional titles
    # Pattern: ## Title (optional) followed by ```hcl code block
    sections = re.split(r"##\s+", markdown)

    for section in sections:
        # Check if this section contains a code block
        code_match = re.search(
            r"```(?:hcl|terraform)?\s*\n(.*?)```", section, re.DOTALL
        )

        if code_match:
            code = code_match.group(1).strip()

            # Extract title from the beginning of the section
            title_match = re.match(r"([^\n]+)", section)
            title = title_match.group(1).strip() if title_match else "Example"

            # Clean up title (remove "Usage", "Example", etc. prefixes if standalone)
            title = re.sub(
                r"^(Usage|Example)\s*$", "Example", title, flags=re.IGNORECASE
            )

            # Extract description (text between title and code block)
            desc_match = re.search(r"^[^\n]+\n+(.*?)```", section, re.DOTALL)
            description = None
            if desc_match:
                desc_text = desc_match.group(1).strip()
                if desc_text and len(desc_text) < 200:
                    description = desc_text

            examples.append(
                ProviderResourceExample(
                    title=title,
                    code=code,
                    description=description,
                )
            )

    return examples


def extract_related_resources(
    markdown: str, current_slug: str
) -> list[RelatedResource]:
    """
    Extract related resource references from markdown.

    Args:
        markdown: Provider documentation markdown
        current_slug: Current resource slug to exclude

    Returns:
        List of related resources
    """
    related = []

    # Find resource/data source references in the markdown
    # Pattern: ibm_xxx or references to other resources
    resource_pattern = r"`(ibm_[a-z_]+)`"

    found_slugs = set()
    for match in re.finditer(resource_pattern, markdown):
        slug = match.group(1)

        # Remove provider prefix for consistency
        slug = re.sub(r"^ibm_", "", slug)

        # Skip if it's the current resource
        if slug == current_slug:
            continue

        # Add to set to avoid duplicates
        if slug not in found_slugs:
            found_slugs.add(slug)
            related.append(
                RelatedResource(
                    slug=slug,
                    title=f"ibm_{slug}",
                )
            )

    # Limit to most relevant (first 5 mentioned)
    return related[:5]


def parse_provider_markdown(markdown: str, slug: str = "") -> dict[str, Any]:
    """
    Parse Terraform provider markdown into structured data.

    Args:
        markdown: Provider documentation markdown
        slug: Resource slug (for extracting related resources)

    Returns:
        Dictionary with parsed content
    """
    return {
        "description": extract_description(markdown),
        "arguments": extract_arguments(markdown),
        "attributes": extract_attributes(markdown),
        "examples": extract_examples(markdown),
        "related_resources": extract_related_resources(markdown, slug),
    }
