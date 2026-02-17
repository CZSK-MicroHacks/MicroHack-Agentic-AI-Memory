# -----------------------------------------------------------------------------
# Container Apps Environment
# -----------------------------------------------------------------------------

resource "azurerm_container_app_environment" "main" {
  name                       = "cae-${var.project_name}"
  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id

  tags = var.tags
}

# -----------------------------------------------------------------------------
# Container App – Backend
# -----------------------------------------------------------------------------

resource "azurerm_container_app" "backend" {
  name                         = "ca-backend-${var.project_name}"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.app.id
  }

  template {
    min_replicas = 1
    max_replicas = 1

    container {
      name   = "backend"
      image  = "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest"
      cpu    = 0.5
      memory = "1Gi"

      # Azure AI Foundry (OpenAI)
      env {
        name  = "AZURE_OPENAI_ENDPOINT"
        value = azapi_resource.ai_foundry.output.properties.endpoint
      }
      env {
        name  = "AZURE_OPENAI_DEPLOYMENT_NAME"
        value = azapi_resource.deployment_gpt4o_mini.name
      }
      env {
        name  = "AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME"
        value = azapi_resource.deployment_text_embedding_3_large.name
      }

      # Azure AI Search
      env {
        name  = "AZURE_SEARCH_ENDPOINT"
        value = "https://${azurerm_search_service.main.name}.search.windows.net"
      }
      env {
        name  = "AZURE_SEARCH_KNOWLEDGE_BASE_NAME"
        value = "customer-support-kb"
      }

      # Cosmos DB
      env {
        name  = "COSMOS_ENDPOINT"
        value = azurerm_cosmosdb_account.main.endpoint
      }
      env {
        name  = "COSMOS_DATABASE_NAME"
        value = azurerm_cosmosdb_sql_database.main.name
      }
      env {
        name  = "COSMOS_CONTAINER_NAME"
        value = azurerm_cosmosdb_sql_container.conversations.name
      }
      env {
        name  = "COSMOS_UPM_DATABASE_NAME"
        value = azurerm_cosmosdb_sql_database.main.name
      }
      env {
        name  = "COSMOS_UPM_CONTAINER_NAME"
        value = azurerm_cosmosdb_sql_container.user_profiles.name
      }

      # Managed Identity
      env {
        name  = "AZURE_CLIENT_ID"
        value = azurerm_user_assigned_identity.app.client_id
      }

      # App authentication
      env {
        name  = "AUTH_MODE"
        value = lower(var.auth_mode)
      }
      env {
        name  = "ENTRA_TENANT_ID"
        value = data.azuread_client_config.current.tenant_id
      }
      env {
        name  = "ENTRA_AUDIENCE"
        value = azuread_application.backend_api.client_id
      }
      env {
        name  = "ENTRA_REQUIRED_SCOPES"
        value = "access_as_user"
      }

      # PostgreSQL
      env {
        name  = "PG_HOST"
        value = azurerm_postgresql_flexible_server.main.fqdn
      }
      env {
        name  = "PG_PORT"
        value = "5432"
      }
      env {
        name  = "PG_DATABASE"
        value = azurerm_postgresql_flexible_server_database.appdb.name
      }
      env {
        name  = "PG_AUTH_MODE"
        value = "managed_identity"
      }
      env {
        name  = "PG_AAD_PRINCIPAL_NAME"
        value = azurerm_user_assigned_identity.app.name
      }
    }
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    transport        = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  tags = var.tags

  lifecycle {
    ignore_changes = [
      template[0].container[0].image,
    ]
  }
}

# -----------------------------------------------------------------------------
# Container App – Frontend
# -----------------------------------------------------------------------------

resource "azurerm_container_app" "frontend" {
  name                         = "ca-frontend-${var.project_name}"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.app.id
  }

  template {
    min_replicas = 1
    max_replicas = 1

    container {
      name   = "frontend"
      image  = "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest"
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "BACKEND_URL"
        value = "https://${azurerm_container_app.backend.ingress[0].fqdn}"
      }
      env {
        name  = "AUTH_MODE"
        value = lower(var.auth_mode)
      }
      env {
        name  = "ENTRA_TENANT_ID"
        value = data.azuread_client_config.current.tenant_id
      }
      env {
        name  = "ENTRA_CLIENT_ID"
        value = azuread_application.frontend_spa.client_id
      }
      env {
        name  = "ENTRA_API_SCOPE"
        value = "${one(azuread_application.backend_api.identifier_uris)}/access_as_user"
      }
    }
  }

  ingress {
    external_enabled = true
    target_port      = 8080
    transport        = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  tags = var.tags

  lifecycle {
    ignore_changes = [
      template[0].container[0].image,
    ]
  }
}
