# -----------------------------------------------------------------------------
# Cosmos DB Account (NoSQL API)
# -----------------------------------------------------------------------------

resource "azurerm_cosmosdb_account" "main" {
  name                          = "cosmos-${var.project_name}"
  resource_group_name           = azurerm_resource_group.main.name
  location                      = azurerm_resource_group.main.location
  offer_type                    = "Standard"
  kind                          = "GlobalDocumentDB"
  local_authentication_disabled = true

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = azurerm_resource_group.main.location
    failover_priority = 0
  }

  tags = var.tags
}

# -----------------------------------------------------------------------------
# Cosmos DB SQL Database
# -----------------------------------------------------------------------------

resource "azurerm_cosmosdb_sql_database" "main" {
  name                = "ag-ui-db"
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
  throughput          = var.cosmosdb_throughput
}

# -----------------------------------------------------------------------------
# Cosmos DB Containers
# -----------------------------------------------------------------------------

resource "azurerm_cosmosdb_sql_container" "conversations" {
  name                = "conversations"
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
  database_name       = azurerm_cosmosdb_sql_database.main.name

  partition_key_paths = ["/user_id"]

  indexing_policy {
    indexing_mode = "consistent"

    included_path {
      path = "/*"
    }
  }
}

resource "azurerm_cosmosdb_sql_container" "user_profiles" {
  name                = "user_profiles"
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
  database_name       = azurerm_cosmosdb_sql_database.main.name

  partition_key_paths = ["/user_id"]

  indexing_policy {
    indexing_mode = "consistent"

    included_path {
      path = "/*"
    }
  }
}

resource "azurerm_cosmosdb_sql_container" "conversationhistory" {
  name                  = "conversationhistory"
  resource_group_name   = azurerm_resource_group.main.name
  account_name          = azurerm_cosmosdb_account.main.name
  database_name         = azurerm_cosmosdb_sql_database.main.name
  partition_key_version = 2
  partition_key_paths   = ["/user_id"]

  conflict_resolution_policy {
    mode                          = "LastWriterWins"
    conflict_resolution_path      = "/_ts"
  }

  indexing_policy {
    indexing_mode = "consistent"

    included_path {
      path = "/*"
    }
  }
}
