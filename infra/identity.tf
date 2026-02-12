# -----------------------------------------------------------------------------
# User-Assigned Managed Identity
# -----------------------------------------------------------------------------

resource "azurerm_user_assigned_identity" "app" {
  name                = "id-${var.project_name}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location

  tags = var.tags
}
