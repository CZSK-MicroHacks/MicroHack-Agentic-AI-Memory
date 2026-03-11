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

resource "azurerm_role_assignment" "provider_registration_assignment" {
  scope              = "/subscriptions/${var.subscription_id}"
  role_definition_id = azurerm_role_definition.provider_registration.role_definition_resource_id
  principal_id       = var.group_object_id
}
