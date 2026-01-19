# Data source for resource group
data "ibm_resource_group" "resource_group" {
  name = var.resource_group_name
}

# Create Code Engine project
resource "ibm_code_engine_project" "project" {
  name              = var.project_name
  resource_group_id = data.ibm_resource_group.resource_group.id
}

# Create Container Registry namespace
resource "ibm_cr_namespace" "namespace" {
  name              = var.container_registry_namespace
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
    server   = "us.icr.io"
  }
}

# Create secret for GitHub token
resource "ibm_code_engine_secret" "app_secrets" {
  project_id = ibm_code_engine_project.project.project_id
  name       = "${var.app_name}-secrets"
  format     = "generic"

  data = {
    GITHUB_TOKEN = var.github_token
  }
}

# Create Code Engine build configuration
resource "ibm_code_engine_build" "build" {
  project_id      = ibm_code_engine_project.project.project_id
  name            = "${var.app_name}-build"
  output_image    = var.image_name
  output_secret   = ibm_code_engine_secret.icr_secret.name
  source_url      = var.git_repo
  source_revision = var.git_branch
  source_context_dir = "."
  strategy_type   = "dockerfile"
  strategy_spec_file = "Dockerfile"
  strategy_size   = "medium"
  timeout         = 900
}

# Note: Build runs must be triggered separately via CLI or API
# as they are one-time operations. The terraform resource doesn't
# support automatic build run triggers.

# Create Code Engine application
resource "ibm_code_engine_app" "app" {
  project_id = ibm_code_engine_project.project.project_id
  name       = var.app_name

  image_reference = var.image_name
  image_secret    = ibm_code_engine_secret.icr_secret.name

  # Resource allocation
  scale_cpu_limit      = var.cpu
  scale_memory_limit   = var.memory
  scale_min_instances  = var.min_scale
  scale_max_instances  = var.max_scale

  # Health probes
  probe_liveness {
    type             = "http"
    path             = "/health"
    port             = var.port
    initial_delay    = 5
    interval         = 30
    timeout          = 10
    failure_threshold = 3
  }

  probe_readiness {
    type             = "http"
    path             = "/health"
    port             = var.port
    initial_delay    = 5
    interval         = 10
    timeout          = 10
    failure_threshold = 3
  }

  # Environment variables from secret
  run_env_variables {
    type      = "secret_full_reference"
    reference = ibm_code_engine_secret.app_secrets.name
  }

  # Additional environment variables
  run_env_variables {
    type  = "literal"
    name  = "TIM_LOG_LEVEL"
    value = var.log_level
  }

  run_env_variables {
    type  = "literal"
    name  = "TIM_ALLOWED_NAMESPACES"
    value = var.allowed_namespaces
  }

  # Ensure build is created first
  depends_on = [
    ibm_code_engine_build.build,
    ibm_code_engine_secret.app_secrets,
    ibm_code_engine_secret.icr_secret
  ]

  # Increase timeout to allow for image build
  timeouts {
    create = "5m"
    update = "5m"
  }

  # Lifecycle: allow app to be created even if not immediately ready
  lifecycle {
    ignore_changes = [status, status_details]
  }
}
