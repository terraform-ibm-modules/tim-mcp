output "project_id" {
  description = "Code Engine project ID"
  value       = ibm_code_engine_project.project.project_id
}

output "project_name" {
  description = "Code Engine project name"
  value       = ibm_code_engine_project.project.name
}

output "app_url" {
  description = "Application URL"
  value       = ibm_code_engine_app.app.endpoint
}

output "app_internal_url" {
  description = "Internal application URL (within Code Engine)"
  value       = ibm_code_engine_app.app.endpoint_internal
}

output "build_name" {
  description = "Code Engine build configuration name"
  value       = ibm_code_engine_build.build.name
}

output "registry_namespace" {
  description = "Container Registry namespace"
  value       = ibm_cr_namespace.namespace.name
}

output "health_endpoint" {
  description = "Health check endpoint URL"
  value       = "${ibm_code_engine_app.app.endpoint}/health"
}
