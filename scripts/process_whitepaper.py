#!/usr/bin/env python3
"""Download and process IBM Cloud Terraform white paper from source markdown.

This script downloads the white paper markdown from the IBM Cloud documentation
repository, processes it by replacing template variables with actual values from
keywords.yml, removes Jekyll metadata, and saves the result to static/terraform-white-paper.md.
"""

import re
from pathlib import Path
import httpx
import yaml


def load_keyword_mappings():
    """Load keyword mappings from the local keyword.yml file."""
    keyword_path = Path(__file__).parent.parent / "keywords.yml"
    
    try:
        if not keyword_path.exists():
            print(f"Warning: keyword.yml not found at {keyword_path}")
            return {}
        
        with open(keyword_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            # Extract just the keyword mappings
            keyword_dict = data.get('keyword', {})
            print(f"Loaded {len(keyword_dict)} keyword mappings")
            return keyword_dict
    except Exception as e:
        print(f"Warning: Could not load keyword mappings: {e}")
        return {}


def process_markdown(text, keywords):
    """Process markdown to replace template variables and clean up."""
    
    # Replace {{site.data.keyword.XXX}} with actual values
    def replace_keyword(match):
        key = match.group(1)
        replacement = keywords.get(key, match.group(0))
        return replacement
    
    text = re.sub(r'\{\{site\.data\.keyword\.([^}]+)\}\}', replace_keyword, text)
    
    # Remove ALL Jekyll metadata blocks starting with {:
    # This matches any line that starts with {: and ends with }
    text = re.sub(r'\{:[^}]+\}\n?', '', text)
    
    # Remove the YAML frontmatter block (between --- delimiters)
    text = re.sub(r'^---\n.*?\n---\n', '', text, flags=re.DOTALL | re.MULTILINE)
    
    # Strip leading/trailing whitespace
    text = text.strip()
    
    return text


def main():
    """Download and process the IBM Cloud Terraform white paper.
    
    Downloads the white paper from GitHub, replaces template variables,
    removes Jekyll metadata, and saves to static/terraform-white-paper.md.
    """
    markdown_url = "https://raw.githubusercontent.com/ibm-cloud-docs/terraform-on-ibm-cloud/refs/heads/master/white-paper.md"
    static_dir = Path(__file__).parent.parent / "static"
    markdown_path = static_dir / "terraform-white-paper.md"
    
    print("Loading keyword mappings...")
    keywords = load_keyword_mappings()
    
    # Download markdown
    print(f"Downloading markdown from {markdown_url}...")
    response = httpx.get(markdown_url, follow_redirects=True)
    response.raise_for_status()
    
    markdown_content = response.text
    print(f"Downloaded {len(markdown_content)} characters")
    
    # Process the markdown
    print("Processing markdown...")
    processed_content = process_markdown(markdown_content, keywords)
    
    # Add header
    final_content = f"""# IBM Cloud Terraform Best Practices

*Source: https://cloud.ibm.com/docs/terraform-on-ibm-cloud*

{processed_content}
"""
    
    # Save to file
    static_dir.mkdir(exist_ok=True)
    markdown_path.write_text(final_content, encoding="utf-8")
    print(f"Created markdown file: {markdown_path}")
    print(f"Final content: {len(final_content)} characters")


if __name__ == "__main__":
    main()