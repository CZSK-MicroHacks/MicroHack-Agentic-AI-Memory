# -----------------------------------------------------------------------------
# Azure Entra ID Applications (Backend API + Frontend SPA)
# -----------------------------------------------------------------------------

locals {
  frontend_default_redirect_uris = compact([
    "http://localhost:5175/",
    var.frontend_redirect_uri,
  ])
  frontend_redirect_uris = distinct(concat(local.frontend_default_redirect_uris, var.frontend_additional_redirect_uris))
  post_logout_redirect_uris = distinct(concat(local.frontend_default_redirect_uris, var.frontend_additional_post_logout_redirect_uris))
}

resource "random_uuid" "backend_access_scope_id" {}

resource "azuread_application" "backend_api" {
  display_name     = "app-${var.project_name}-backend-api"
  sign_in_audience = "AzureADMyOrg"

  identifier_uris = [
    "api://${var.project_name}-${data.azuread_client_config.current.tenant_id}"
  ]

  api {
    requested_access_token_version = 2

    oauth2_permission_scope {
      admin_consent_description  = "Allow the frontend app to call the backend API as the signed-in user."
      admin_consent_display_name = "Access backend API"
      enabled                    = true
      id                         = random_uuid.backend_access_scope_id.result
      type                       = "User"
      user_consent_description   = "Allow this app to access the backend API on your behalf."
      user_consent_display_name  = "Access backend API"
      value                      = "access_as_user"
    }
  }
}

resource "azuread_service_principal" "backend_api" {
  client_id = azuread_application.backend_api.client_id
}

resource "azuread_application" "frontend_spa" {
  display_name     = "app-${var.project_name}-frontend-spa"
  sign_in_audience = "AzureADMyOrg"

  single_page_application {
    redirect_uris = local.frontend_redirect_uris
  }

  web {
    logout_url = length(local.post_logout_redirect_uris) > 0 ? local.post_logout_redirect_uris[0] : null
  }

  required_resource_access {
    resource_app_id = azuread_application.backend_api.client_id

    resource_access {
      id   = random_uuid.backend_access_scope_id.result
      type = "Scope"
    }
  }
}

resource "azuread_service_principal" "frontend_spa" {
  client_id = azuread_application.frontend_spa.client_id
}

resource "azuread_service_principal_delegated_permission_grant" "frontend_to_backend" {
  service_principal_object_id          = azuread_service_principal.frontend_spa.object_id
  resource_service_principal_object_id = azuread_service_principal.backend_api.object_id
  claim_values                         = ["access_as_user"]
}
