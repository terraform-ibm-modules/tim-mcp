"""
Service for interacting with Terraform module GitHub repositories
"""

import requests
import re
from typing import Dict, Any, Tuple, Optional

from services.terraform_registry import TerraformRegistryService


class TerraformGitHubService:
    @staticmethod
    def parse_module_id(module_id: str) -> Tuple[str, str, str, Optional[str]]:
        """Parse a module ID into its components"""
        module_parts = module_id.split('/')
        if len(module_parts) < 3:
            raise ValueError(f"Invalid module ID format. Expected format: namespace/name/provider[/version]")
        
        namespace = module_parts[0]
        name = module_parts[1]
        provider = module_parts[2]
        version = module_parts[3] if len(module_parts) > 3 else None
        
        return namespace, name, provider, version
    
    @staticmethod
    def get_latest_version(namespace: str, name: str, provider: str) -> str:
        """Get the latest version of a module"""
        url = f"{TerraformRegistryService.BASE_URL}/{namespace}/{name}/{provider}"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return data.get("version", "")
    
    @staticmethod
    def get_module_file(module_id: str, path: str, file_name: str = "main.tf") -> Dict[str, Any]:
        """
        Fetch a file from a Terraform module GitHub repository.
        
        Args:
            module_id: The ID of the Terraform module (e.g., terraform-ibm-modules/base-ocp-vpc/ibm)
            path: The path to the directory containing the file (e.g., examples/advanced)
            file_name: The name of the file to fetch (default: main.tf)
            
        Returns:
            Dictionary with the fetched file content and metadata
        """
        try:
            # Extract module components
            namespace, name, provider, version = TerraformGitHubService.parse_module_id(module_id)
            
            # If no version is provided, try to get the latest version
            if not version:
                try:
                    version = TerraformGitHubService.get_latest_version(namespace, name, provider)
                except Exception as e:
                    return {
                        "error": True,
                        "message": f"Error fetching module version: {str(e)}",
                        "module_id": module_id
                    }
            
            # Construct GitHub URL for the file
            # Notice that terraform-ibm- is added in front of name in Github world. Also v is used in front of version names in GitHub.
            github_url = f"https://raw.githubusercontent.com/{namespace}/terraform-ibm-{name}/refs/tags/v{version}/{path}/{file_name}"
            
            # Fetch the file from GitHub
            response = requests.get(github_url)
            response.raise_for_status()
            file_content = response.text
            
            # If this is a Terraform file, replace source references
            if file_name.endswith('.tf'):
                # Replace source = "../.." or source = "../../" with source = "{namespace}/{name}" and add version
                file_content = re.sub(
                    r'source\s*=\s*"\.\.\/\.\.\/?"',
                    f'source = "{namespace}/{name}"\n  version = "{version}"',
                    file_content
                )
            
            return {
                "module_id": module_id,
                "path": path,
                "file_name": file_name,
                "version": version,
                "content": file_content
            }
        except Exception as e:
            return {
                "error": True,
                "message": f"Error fetching file: {str(e)}",
                "module_id": module_id,
                "path": path,
                "file_name": file_name
            }
