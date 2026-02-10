output "project_id" {
  description = "Code Engine project ID"
  value       = module.code_engine.project_id
}

output "build" {
  description = "Code Engine build configuration"
  value       = module.code_engine.build
  sensitive   = true
}
