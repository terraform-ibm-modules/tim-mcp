"""
Service for interacting with Terraform Registry API
"""

import requests
from typing import List, Dict, Any, Optional

from models.terraform_module import TerraformModuleSearchResult, TerraformModuleDetail


class TerraformRegistryService:
    BASE_URL = "https://registry.terraform.io/v1/modules"
    
    @staticmethod
    def search_modules(query: str, namespace: str = "terraform-ibm-modules", limit: Optional[int] = 2) -> List[TerraformModuleSearchResult]:
        """Search for Terraform modules in the specified namespace"""
        url = f"{TerraformRegistryService.BASE_URL}/search"
        params = {
            "q": query,
            "namespace": namespace,
            "limit": limit if limit is not None else 5
        }
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        modules = data.get("modules", [])
        
        return [TerraformModuleSearchResult(module) for module in modules]
    
    @staticmethod
    def get_module_by_id(module_id: str) -> TerraformModuleDetail:
        """Get detailed information about a specific module by ID"""
        url = f"{TerraformRegistryService.BASE_URL}/{module_id}"
        
        response = requests.get(url)
        response.raise_for_status()
        
        data = response.json()
        return TerraformModuleDetail(data)
