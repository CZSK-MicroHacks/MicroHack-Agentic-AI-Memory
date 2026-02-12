# -----------------------------------------------------------------------------
# Role Assignments
# -----------------------------------------------------------------------------

# Cosmos DB Built-in Data Contributor — allows full CRUD on data plane
# This is the built-in role ID for "Cosmos DB Built-in Data Contributor"
resource "azurerm_cosmosdb_sql_role_assignment" "mi_data_contributor" {
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
  # Built-in "Cosmos DB Built-in Data Contributor" role definition ID
  role_definition_id = "${azurerm_cosmosdb_account.main.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
  principal_id       = azurerm_user_assigned_identity.app.principal_id
  scope              = azurerm_cosmosdb_account.main.id
}

# AcrPull — allows managed identity to pull images from ACR
resource "azurerm_role_assignment" "mi_acr_pull" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

# Azure AI User — allows managed identity to call Azure AI Foundry
resource "azurerm_role_assignment" "mi_ai_user" {
  scope                = azapi_resource.ai_foundry.id
  role_definition_name = "Azure AI User"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}
