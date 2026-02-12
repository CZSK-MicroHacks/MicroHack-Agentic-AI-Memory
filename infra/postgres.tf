# -----------------------------------------------------------------------------
# PostgreSQL Flexible Server
# -----------------------------------------------------------------------------

resource "azurerm_postgresql_flexible_server" "main" {
  name                          = "pgflex-${var.project_name}"
  resource_group_name           = azurerm_resource_group.main.name
  location                      = var.postgres_location
  version                       = var.postgres_version
  administrator_login           = var.postgres_admin_login
  administrator_password        = var.postgres_admin_password
  sku_name                      = var.postgres_sku
  storage_mb                    = var.postgres_storage_mb
  backup_retention_days         = 7
  geo_redundant_backup_enabled  = false
  public_network_access_enabled = true

  authentication {
    active_directory_auth_enabled = true
    password_auth_enabled         = true
    tenant_id                     = data.azurerm_client_config.current.tenant_id
  }

  tags = var.tags
}

# Enable pgvector extension
resource "azurerm_postgresql_flexible_server_configuration" "pgvector" {
  name      = "azure.extensions"
  server_id = azurerm_postgresql_flexible_server.main.id
  value     = "VECTOR"
}

# Firewall rule: allow Azure services
resource "azurerm_postgresql_flexible_server_firewall_rule" "allow_azure" {
  name      = "AllowAzureServices"
  server_id = azurerm_postgresql_flexible_server.main.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

# Database
resource "azurerm_postgresql_flexible_server_database" "appdb" {
  name      = "appdb"
  server_id = azurerm_postgresql_flexible_server.main.id
  collation = "en_US.utf8"
  charset   = "UTF8"
}

# AAD Admin — Managed Identity
resource "azurerm_postgresql_flexible_server_active_directory_administrator" "mi_admin" {
  server_name         = azurerm_postgresql_flexible_server.main.name
  resource_group_name = azurerm_resource_group.main.name
  tenant_id           = data.azurerm_client_config.current.tenant_id
  object_id           = azurerm_user_assigned_identity.app.principal_id
  principal_name      = azurerm_user_assigned_identity.app.name
  principal_type      = "ServicePrincipal"
}
