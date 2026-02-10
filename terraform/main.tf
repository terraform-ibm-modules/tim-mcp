data "ibm_resource_group" "resource_group" {
  name = var.resource_group_name
}

module "code_engine" {
  source            = "terraform-ibm-modules/code-engine/ibm"
  version           = "4.7.26"
  ibmcloud_api_key  = var.ibmcloud_api_key
  resource_group_id = data.ibm_resource_group.resource_group.id
  project_name      = var.name

  builds = {
    "${var.name}-build" = {
      source_url                   = var.git_repo
      source_revision              = var.git_branch
      strategy_type                = "dockerfile"
      strategy_size                = "medium"
      timeout                      = 1800
      container_registry_namespace = var.name
      prefix                       = ""
      region                       = var.region
    }
  }

  secrets = {
    "${var.name}-secrets" = {
      format = "generic"
      data = {
        GITHUB_TOKEN = var.github_token
      }
    }
  }
}
