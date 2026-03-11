data "azuread_client_config" "current" {}

resource "azuread_group" "users" {
  display_name     = var.group_name
  security_enabled = true
}

resource "azuread_user" "users" {
  for_each = local.user_map

  user_principal_name   = each.value.upn
  display_name          = each.value.display
  password              = var.password
  force_password_change = false
  mail_nickname         = each.value.nickname
}

resource "azuread_group_member" "members" {
  for_each = azuread_user.users

  group_object_id  = azuread_group.users.object_id
  member_object_id = each.value.object_id
}

resource "random_uuid" "backend_access_scope_id" {
  for_each = local.user_map
}

resource "azuread_application" "backend_api" {
  for_each = local.user_map

  display_name     = each.value.backend_app_name
  sign_in_audience = "AzureADMyOrg"

  identifier_uris = [
    each.value.backend_identifier_uri
  ]

  api {
    requested_access_token_version = 2

    oauth2_permission_scope {
      admin_consent_description  = "Allow the frontend app to call the backend API as the signed-in user."
      admin_consent_display_name = "Access backend API"
      enabled                    = true
      id                         = random_uuid.backend_access_scope_id[each.key].result
      type                       = "User"
      user_consent_description   = "Allow this app to access the backend API on your behalf."
      user_consent_display_name  = "Access backend API"
      value                      = "access_as_user"
    }
  }
}

resource "azuread_service_principal" "backend_api" {
  for_each = local.user_map

  client_id = azuread_application.backend_api[each.key].client_id
}

resource "azuread_application" "frontend_spa" {
  for_each = local.user_map

  display_name     = each.value.frontend_app_name
  sign_in_audience = "AzureADMyOrg"

  single_page_application {
    redirect_uris = local.frontend_redirect_uris
  }

  web {
    logout_url = length(local.post_logout_redirect_uris) > 0 ? local.post_logout_redirect_uris[0] : null
  }

  required_resource_access {
    resource_app_id = azuread_application.backend_api[each.key].client_id

    resource_access {
      id   = random_uuid.backend_access_scope_id[each.key].result
      type = "Scope"
    }
  }
}

resource "azuread_service_principal" "frontend_spa" {
  for_each = local.user_map

  client_id = azuread_application.frontend_spa[each.key].client_id
}

resource "azuread_service_principal_delegated_permission_grant" "frontend_to_backend" {
  for_each = local.user_map

  service_principal_object_id          = azuread_service_principal.frontend_spa[each.key].object_id
  resource_service_principal_object_id = azuread_service_principal.backend_api[each.key].object_id
  claim_values                         = ["access_as_user"]
}
