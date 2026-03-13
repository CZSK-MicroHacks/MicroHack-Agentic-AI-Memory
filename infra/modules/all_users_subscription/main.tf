resource "azurerm_role_definition" "provider_registration" {
  name        = "Resource Provider Registration"
  scope       = "/subscriptions/${var.subscription_id}"
  description = "Allows workshop users to register and unregister Azure resource providers."

  permissions {
    actions = [
      "*/register/action",
      "*/unregister/action",
    ]
    not_actions = []
  }

  assignable_scopes = [
    "/subscriptions/${var.subscription_id}"
  ]
}

locals {
  subscription_scope = "/subscriptions/${var.subscription_id}"

  builtin_role_names = toset([
    "Storage Blob Data Owner",
    "Azure AI Owner",
    "Search Service Contributor",
    "Search Index Data Contributor",
    "Search Index Data Reader",
  ])
}

resource "azurerm_role_assignment" "provider_registration_assignment" {
  scope              = local.subscription_scope
  role_definition_id = azurerm_role_definition.provider_registration.role_definition_resource_id
  principal_id       = var.group_object_id
}

resource "azurerm_role_assignment" "builtin_subscription_roles" {
  for_each = local.builtin_role_names

  scope                = local.subscription_scope
  role_definition_name = each.value
  principal_id         = var.group_object_id
}
