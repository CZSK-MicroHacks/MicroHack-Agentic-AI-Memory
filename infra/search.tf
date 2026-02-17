# -----------------------------------------------------------------------------
# Azure AI Search
# -----------------------------------------------------------------------------

resource "azurerm_search_service" "main" {
  name                          = "search-${var.project_name}"
  resource_group_name           = azurerm_resource_group.main.name
  location                      = var.search_location
  sku                           = var.search_sku
  semantic_search_sku           = "standard"
  local_authentication_enabled  = false

  identity {
    type = "SystemAssigned"
  }

  tags = var.tags
}
