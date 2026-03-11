locals {
  user_indices = range(1, var.n + 1)
  user_map = {
    for index in local.user_indices : tostring(index) => {
      padded                 = format("%03d", index)
      project_name           = "${var.project_name}${format("%03d", index)}"
      upn                    = "user${format("%03d", index)}@${var.domain}"
      display                = "User ${format("%03d", index)}"
      nickname               = "user${format("%03d", index)}"
      backend_app_name       = "app-${var.project_name}${format("%03d", index)}-backend-api"
      frontend_app_name      = "app-${var.project_name}${format("%03d", index)}-frontend-spa"
      backend_identifier_uri = "api://${var.project_name}${format("%03d", index)}-${var.domain}"
    }
  }

  frontend_default_redirect_uris = compact([
    "http://localhost:5175/",
    var.frontend_redirect_uri,
  ])

  frontend_redirect_uris = distinct(concat(
    local.frontend_default_redirect_uris,
    var.frontend_additional_redirect_uris,
  ))

  post_logout_redirect_uris = distinct(concat(
    local.frontend_default_redirect_uris,
    var.frontend_additional_post_logout_redirect_uris,
  ))
}
