# Data source for resource group
data "ibm_resource_group" "resource_group" {
  name = var.resource_group_name
}

# Construct full image name
locals {
  image_name = "${var.registry}/${var.namespace}/${var.name}:${var.tag}"
}

# Create Code Engine project
resource "ibm_code_engine_project" "project" {
  name              = var.name
  resource_group_id = data.ibm_resource_group.resource_group.id
}

# Create Container Registry namespace
resource "ibm_cr_namespace" "namespace" {
  name              = var.namespace
  resource_group_id = data.ibm_resource_group.resource_group.id
}

# Create registry secret for accessing IBM Container Registry
resource "ibm_code_engine_secret" "icr_secret" {
  project_id = ibm_code_engine_project.project.project_id
  name       = "icr-secret"
  format     = "registry"

  data = {
    username = "iamapikey"
    password = var.ibmcloud_api_key
    server   = var.registry
  }
}

# Create secret for GitHub token
resource "ibm_code_engine_secret" "app_secrets" {
  project_id = ibm_code_engine_project.project.project_id
  name       = "${var.name}-secrets"
  format     = "generic"

  data = {
    GITHUB_TOKEN = var.github_token
  }
}

# Create Code Engine build configuration
resource "ibm_code_engine_build" "build" {
  project_id      = ibm_code_engine_project.project.project_id
  name            = "${var.name}-build"
  output_image    = local.image_name
  output_secret   = ibm_code_engine_secret.icr_secret.name
  source_url      = var.git_repo
  source_revision = var.git_branch
  source_context_dir = "."
  strategy_type   = "dockerfile"
  strategy_spec_file = "Dockerfile"
  strategy_size   = "medium"
  timeout         = 1800  # 30 minutes for UBI8 builds
}

# Note: Build runs must be triggered separately via CLI or API
# as they are one-time operations. The terraform resource doesn't
# support automatic build run triggers.

# Note: App is managed via CLI in the deployment script instead of Terraform
# due to Terraform provider issues with app creation timing and status polling.
# The ibm_code_engine_app resource has been removed to avoid these issues.
# The deployment script uses 'ibmcloud ce app create/update' instead.
