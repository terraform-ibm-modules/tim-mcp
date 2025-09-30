#!/usr/bin/env python3
"""Simple script to download and convert IBM Cloud Terraform PDF to markdown using PyMuPDF."""

import re
from pathlib import Path
import httpx
import fitz  # PyMuPDF

def clean_and_format_text(text):
    """Clean and format text extracted from PDF."""
    lines = text.split('\n')
    formatted_lines = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Skip page numbers and headers/footers
        if re.match(r'^\d+$', line) or line.startswith('Best practices for Terraform on IBM Cloud'):
            continue
            
        # Handle section headers (lines that are all caps or title case without periods)
        if (line.isupper() and len(line) > 3) or (line.istitle() and not line.endswith('.')):
            formatted_lines.append(f"\n## {line}\n")
        # Handle numbered lists
        elif re.match(r'^\d+\.', line):
            formatted_lines.append(f"\n{line}")
        # Handle bullet points
        elif line.startswith('•') or line.startswith('-'):
            formatted_lines.append(f"\n{line}")
        # Regular paragraphs
        else:
            # If the previous line ended with a period and this starts with capital, it's a new paragraph
            if formatted_lines and formatted_lines[-1].strip().endswith('.') and line[0].isupper():
                formatted_lines.append(f"\n{line}")
            else:
                formatted_lines.append(line)
    
    # Join and clean up
    text = '\n'.join(formatted_lines)
    
    # Clean up excessive newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()

def main():
    """Download PDF and convert to markdown."""
    url = "https://cloud.ibm.com/media/docs/pdf/terraform-on-ibm-cloud/white-paper.pdf"
    static_dir = Path(__file__).parent.parent / "static"
    pdf_path = static_dir / "terraform-white-paper.pdf"
    markdown_path = static_dir / "terraform-white-paper.md"
    
    # Download PDF
    print(f"Downloading PDF from {url}...")
    response = httpx.get(url, follow_redirects=True)
    response.raise_for_status()
    
    static_dir.mkdir(exist_ok=True)
    pdf_path.write_bytes(response.content)
    print(f"Downloaded to {pdf_path}")
    
    # Extract text using PyMuPDF
    print("Extracting text from PDF...")
    doc = fitz.open(pdf_path)
    full_text = ""
    
    for page in doc:
        # Get text blocks which preserves more structure
        blocks = page.get_text("blocks")
        page_text = ""
        
        for block in blocks:
            if len(block) >= 5:  # Text block
                block_text = block[4].strip()
                if block_text:
                    page_text += block_text + "\n"
        
        if page_text.strip():
            full_text += page_text + "\n"
    
    doc.close()
    
    # Clean and format the text
    cleaned_text = clean_and_format_text(full_text)
    
    # Create markdown
    markdown_content = f"""# IBM Cloud Terraform Best Practices

*Source: {url}*

{cleaned_text}
"""
    
    markdown_path.write_text(markdown_content, encoding="utf-8")
    print(f"Created properly formatted markdown file: {markdown_path}")

if __name__ == "__main__":
    main()