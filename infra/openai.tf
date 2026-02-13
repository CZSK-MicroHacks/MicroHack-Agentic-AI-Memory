# -----------------------------------------------------------------------------
# Azure AI Foundry (Microsoft.CognitiveServices/accounts – AIServices)
# -----------------------------------------------------------------------------

resource "azapi_resource" "ai_foundry" {
  type                      = "Microsoft.CognitiveServices/accounts@2025-06-01"
  name                      = "aifoundry-${var.project_name}"
  parent_id                 = azurerm_resource_group.main.id
  location                  = var.location
  schema_validation_enabled = false

  body = {
    kind = "AIServices"
    sku = {
      name = "S0"
    }
    identity = {
      type = "SystemAssigned"
    }
    properties = {
      disableLocalAuth        = true
      allowProjectManagement  = true
      customSubDomainName     = "aifoundry-${var.project_name}"
    }
  }

  response_export_values = ["properties.endpoint"]

  tags = var.tags
}

# -----------------------------------------------------------------------------
# AI Foundry Project
# -----------------------------------------------------------------------------

resource "azapi_resource" "ai_foundry_project" {
  type                      = "Microsoft.CognitiveServices/accounts/projects@2025-06-01"
  name                      = "project-${var.project_name}"
  parent_id                 = azapi_resource.ai_foundry.id
  location                  = var.location
  schema_validation_enabled = false

  body = {
    sku = {
      name = "S0"
    }
    identity = {
      type = "SystemAssigned"
    }
    properties = {
      displayName = "AG-UI Demo Project"
      description = "AI Foundry project for ag-ui-demo"
    }
  }
}

# -----------------------------------------------------------------------------
# Model Deployments
# -----------------------------------------------------------------------------

resource "azapi_resource" "deployment_gpt4o_mini" {
  type      = "Microsoft.CognitiveServices/accounts/deployments@2023-05-01"
  name      = "gpt-4o-mini"
  parent_id = azapi_resource.ai_foundry.id

  body = {
    sku = {
      name     = "GlobalStandard"
      capacity = 30
    }
    properties = {
      model = {
        format  = "OpenAI"
        name    = "gpt-4o-mini"
        version = "2024-07-18"
      }
    }
  }

  depends_on = [azapi_resource.ai_foundry]
}

resource "azapi_resource" "deployment_text_embedding_3_large" {
  type      = "Microsoft.CognitiveServices/accounts/deployments@2023-05-01"
  name      = "text-embedding-3-large"
  parent_id = azapi_resource.ai_foundry.id

  body = {
    sku = {
      name     = "GlobalStandard"
      capacity = 30
    }
    properties = {
      model = {
        format  = "OpenAI"
        name    = "text-embedding-3-large"
        version = "1"
      }
    }
  }

  depends_on = [azapi_resource.deployment_gpt4o_mini]
}
