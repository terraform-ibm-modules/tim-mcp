variable "ibmcloud_api_key" {
  description = "IBM Cloud API key for authentication"
  type        = string
  sensitive   = true
}

variable "region" {
  description = "IBM Cloud region for Code Engine project"
  type        = string
  default     = "us-south"
}

variable "resource_group_name" {
  description = "Name of the IBM Cloud resource group"
  type        = string
  default     = "Default"
}

variable "name" {
  description = "Name of the Code Engine project and application"
  type        = string
  default     = "tim-mcp"
}

variable "github_token" {
  description = "GitHub Personal Access Token for API access"
  type        = string
  sensitive   = true
}

variable "git_repo" {
  description = "Git repository URL for Code Engine build"
  type        = string
  default     = "https://github.com/terraform-ibm-modules/tim-mcp"
}

variable "git_branch" {
  description = "Git branch to build from"
  type        = string
  default     = "main"
}
