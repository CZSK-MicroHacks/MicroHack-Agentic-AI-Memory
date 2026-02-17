# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

# Resource Group
output "resource_group_name" {
  value = azurerm_resource_group.main.name
}

# Managed Identity
output "managed_identity_id" {
  value = azurerm_user_assigned_identity.app.id
}

output "managed_identity_client_id" {
  value = azurerm_user_assigned_identity.app.client_id
}

output "managed_identity_principal_id" {
  value = azurerm_user_assigned_identity.app.principal_id
}

# Application Insights
output "appinsights_connection_string" {
  value     = azurerm_application_insights.main.connection_string
  sensitive = true
}

output "appinsights_instrumentation_key" {
  value     = azurerm_application_insights.main.instrumentation_key
  sensitive = true
}

# Container Apps
output "backend_fqdn" {
  value = azurerm_container_app.backend.ingress[0].fqdn
}

output "frontend_fqdn" {
  value = azurerm_container_app.frontend.ingress[0].fqdn
}

output "container_app_environment_id" {
  value = azurerm_container_app_environment.main.id
}

# PostgreSQL
output "postgres_fqdn" {
  value = azurerm_postgresql_flexible_server.main.fqdn
}

output "postgres_database" {
  value = azurerm_postgresql_flexible_server_database.appdb.name
}

# Cosmos DB
output "cosmosdb_endpoint" {
  value = azurerm_cosmosdb_account.main.endpoint
}

output "cosmosdb_database" {
  value = azurerm_cosmosdb_sql_database.main.name
}

# Redis
output "redis_hostname" {
  value = azurerm_redis_cache.main.hostname
}

output "redis_port" {
  value = azurerm_redis_cache.main.ssl_port
}

output "redis_primary_key" {
  value     = azurerm_redis_cache.main.primary_access_key
  sensitive = true
}

# ACR
output "acr_login_server" {
  value = azurerm_container_registry.main.login_server
}

output "acr_name" {
  value = azurerm_container_registry.main.name
}

# Azure AI Foundry
output "ai_foundry_endpoint" {
  value = azapi_resource.ai_foundry.output.properties.endpoint
}

output "ai_foundry_name" {
  value = azapi_resource.ai_foundry.name
}

output "ai_foundry_project_name" {
  value = azapi_resource.ai_foundry_project.name
}

output "openai_chat_deployment" {
  value = azapi_resource.deployment_gpt4o_mini.name
}

output "openai_embedding_deployment" {
  value = azapi_resource.deployment_text_embedding_3_large.name
}

# Azure AI Search
output "search_endpoint" {
  value = "https://${azurerm_search_service.main.name}.search.windows.net"
}

output "search_name" {
  value = azurerm_search_service.main.name
}

# Entra ID app registrations
output "entra_tenant_id" {
  value = data.azuread_client_config.current.tenant_id
}

output "backend_api_client_id" {
  value = azuread_application.backend_api.client_id
}

output "frontend_spa_client_id" {
  value = azuread_application.frontend_spa.client_id
}

output "backend_api_scope" {
  value = "${one(azuread_application.backend_api.identifier_uris)}/access_as_user"
}

output "auth_mode" {
  value = lower(var.auth_mode)
}
