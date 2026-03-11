output "entra_group_object_id" {
  value = module.entra.group_object_id
}

output "user_principal_names" {
  value = module.entra.user_principal_names
}

output "user_object_ids" {
  value = module.entra.user_object_ids
}

output "resource_group_names" {
  value = { for key, seat in module.user_seats : key => seat.resource_group_name }
}

output "backend_fqdns" {
  value = { for key, seat in module.user_seats : key => seat.backend_fqdn }
}

output "frontend_fqdns" {
  value = { for key, seat in module.user_seats : key => seat.frontend_fqdn }
}

output "backend_api_client_ids" {
  value = module.entra.backend_api_client_ids
}

output "frontend_spa_client_ids" {
  value = module.entra.frontend_spa_client_ids
}

output "backend_api_scopes" {
  value = module.entra.backend_api_scopes
}

output "entra_tenant_id" {
  value = module.entra.tenant_id
}
