output "project_id" {
  description = "Code Engine project ID"
  value       = ibm_code_engine_project.project.project_id
}

output "project_name" {
  description = "Code Engine project name"
  value       = ibm_code_engine_project.project.name
}

output "build_name" {
  description = "Code Engine build configuration name"
  value       = ibm_code_engine_build.build.name
}

output "registry_namespace" {
  description = "Container Registry namespace (computed from user_name)"
  value       = ibm_cr_namespace.namespace.name
}

output "image_name" {
  description = "Full container image name"
  value       = local.image_name
}
