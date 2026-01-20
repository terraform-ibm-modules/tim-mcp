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

variable "project_name" {
  description = "Name of the Code Engine project"
  type        = string
  default     = "tim-mcp"
}

variable "app_name" {
  description = "Name of the Code Engine application"
  type        = string
  default     = "tim-mcp"
}

variable "image_name" {
  description = "Full container image name"
  type        = string
  default     = "us.icr.io/tim-mcp/tim-mcp:latest"
}

variable "github_token" {
  description = "GitHub Personal Access Token for API access"
  type        = string
  sensitive   = true
}

variable "cpu" {
  description = "CPU allocation for the application"
  type        = string
  default     = "0.25"
}

variable "memory" {
  description = "Memory allocation for the application (e.g., 1G, 2G, 4G)"
  type        = string
  default     = "1G"
}

variable "min_scale" {
  description = "Minimum number of instances"
  type        = number
  default     = 1
}

variable "max_scale" {
  description = "Maximum number of instances"
  type        = number
  default     = 3
}

variable "port" {
  description = "Port the application listens on"
  type        = number
  default     = 8080
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

variable "container_registry_namespace" {
  description = "IBM Container Registry namespace"
  type        = string
  default     = "tim-mcp"
}

variable "allowed_namespaces" {
  description = "Comma-separated list of allowed Terraform module namespaces"
  type        = string
  default     = "terraform-ibm-modules"
}

variable "log_level" {
  description = "Application log level"
  type        = string
  default     = "INFO"
}
