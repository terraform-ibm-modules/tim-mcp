"""
Models for Terraform modules
"""

from typing import Dict, Any, List


class TerraformModuleSearchResult:
    def __init__(self, module_data: Dict[str, Any]):
        self.id = module_data.get("id", "")
        self.namespace = module_data.get("namespace", "")
        self.name = module_data.get("name", "")
        self.version = module_data.get("version", "")
        self.provider = module_data.get("provider", "")
        self.description = module_data.get("description", "")
        self.downloads = module_data.get("downloads", 0)
        self.source = module_data.get("source", "")
        self.published_at = module_data.get("published_at", "")

    def to_dict(self) -> Dict[str, Any]:
        """Convert module data to dictionary format"""
        return {
            "id": self.id,
            "name": self.name,
            "namespace": self.namespace,
            "provider": self.provider,
            "version": self.version,
            "description": self.description,
            "downloads": self.downloads,
            "source": self.source,
            "url": f"https://registry.terraform.io/modules/{self.namespace}/{self.name}/{self.provider}"
        }


class TerraformModuleDetail:
    def __init__(self, module_data: Dict[str, Any]):
        self.id = module_data.get("id", "")
        self.namespace = module_data.get("namespace", "")
        self.name = module_data.get("name", "")
        self.version = module_data.get("version", "")
        self.provider = module_data.get("provider", "")
        self.description = module_data.get("description", "")
        self.source = module_data.get("source", "")
        self.published_at = module_data.get("published_at", "")
        self.downloads = module_data.get("downloads", 0)
        
        # Root module data
        self.root = module_data.get("root", {})
        
        # Submodules
        self.submodules = module_data.get("submodules", [])
        
        # Examples
        self.examples = module_data.get("examples", [])
    
    def to_filtered_dict(self) -> Dict[str, Any]:
        """Convert module data to filtered dictionary format for LLM consumption"""
        # Process examples to include only path and readme
        filtered_examples = []
        for example in self.examples:
            filtered_examples.append({
                "path": example.get("path", ""),
                "name": example.get("name", ""),
                "readme": example.get("readme", "")
            })
        
        # Process submodules to include readme
        filtered_submodules = []
        for submodule in self.submodules:
            filtered_submodules.append({
                "path": submodule.get("path", ""),
                "name": submodule.get("name", ""),
                "readme": submodule.get("readme", "")
            })
        
        return {
            "id": self.id,
            "name": self.name,
            "namespace": self.namespace,
            "provider": self.provider,
            "version": self.version,
            "description": self.description,
            "source": self.source,
            "root": {
                "readme": self.root.get("readme", "")
            },
            "submodules": filtered_submodules,
            "examples": filtered_examples
        }
