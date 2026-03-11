output "group_object_id" {
  value = azuread_group.users.object_id
}

output "user_object_ids" {
  value = { for key, user in azuread_user.users : key => user.object_id }
}

output "user_principal_names" {
  value = { for key, user in azuread_user.users : key => user.user_principal_name }
}

output "tenant_id" {
  value = data.azuread_client_config.current.tenant_id
}

output "backend_api_client_ids" {
  value = { for key, app in azuread_application.backend_api : key => app.client_id }
}

output "frontend_spa_client_ids" {
  value = { for key, app in azuread_application.frontend_spa : key => app.client_id }
}

output "backend_api_scopes" {
  value = { for key, app in azuread_application.backend_api : key => "${one(app.identifier_uris)}/access_as_user" }
}
