"""
FastMCP Server for Terraform IBM Modules Search
"""

from fastmcp import FastMCP
from typing import Optional, Dict, Any
import os

# Import models
from models.terraform_module import TerraformModuleSearchResult, TerraformModuleDetail

# Import services
from services.terraform_registry import TerraformRegistryService
from services.terraform_github import TerraformGitHubService

# Read instructions from markdown file
instructions_path = os.path.join(os.path.dirname(__file__), "static", "llm_instructions.md")
with open(instructions_path, "r") as f:
    instructions_content = f.read()

# Create server
mcp = FastMCP("terraform-ibm-modules mcp server",
instructions = instructions_content
)

# URI scheme for module resources
MODULE_URI_SCHEME = "terraform-module"

# Tool for searching Terraform modules
@mcp.tool
def search_terraform_modules(query: str, limit: Optional[int] = 2) -> Dict[str, Any]:
    """
    Search for Terraform modules in the terraform-ibm-modules namespace.
    
    Args:
        query: Search query for finding modules
        limit: Maximum number of results to return (default: 2)
    
    Returns:
        JSON object with search results
    """
    try:
        modules = TerraformRegistryService.search_modules(query, limit=limit if limit is not None else 5)
        
        # Sort by most downloaded first
        modules.sort(key=lambda module: module.downloads, reverse=True)

        result = {
            "query": query,
            "count": len(modules),
            "modules": [module.to_dict() for module in modules]
        }
        
        return result
    except Exception as e:
        return {
            "error": True,
            "message": f"Error searching for modules: {str(e)}",
            "query": query,
            "modules": []
        }

# Tool for getting detailed module information
@mcp.tool
def get_terraform_module(module_id: str) -> Dict[str, Any]:
    """
    Get detailed information about a specific Terraform module.
    
    Args:
        module_id: The ID of the Terraform module (e.g., terraform-ibm-modules/resource-group/ibm/1.3.0)
    
    Returns:
        Filtered module information including description, readme, submodules, and examples
    """
    try:
        
        # Get module details
        module = TerraformRegistryService.get_module_by_id(module_id)
        
        # Return filtered information
        return module.to_filtered_dict()
    except Exception as e:
        return {
            "error": True,
            "message": f"Error fetching module details: {str(e)}",
            "module_id": module_id
        }

# Tool for fetching any file from a Terraform module repository
@mcp.tool
def get_terraform_module_file(module_id: str, path: str, file_name: str = "main.tf") -> Dict[str, Any]:
    """
    Fetch any file from a Terraform module repository based on module ID and path.
    
    Args:
        module_id: The ID of the Terraform module (e.g., terraform-ibm-modules/base-ocp-vpc/ibm)
        path: The path to the directory containing the file (e.g., examples/advanced)
        file_name: The name of the file to fetch (default: main.tf)
    
    Returns:
        JSON object with the fetched file content and metadata
    """
    try:
        return TerraformGitHubService.get_module_file(module_id, path, file_name)
    except Exception as e:
        return {
            "error": True,
            "message": f"Error fetching Terraform module file: {str(e)}",
            "module_id": module_id,
            "path": path,
            "file_name": file_name
        }

if __name__ == "__main__":
    mcp.run()