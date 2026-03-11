locals {
  user_indices      = range(1, var.n + 1)
  region_count      = length(var.locations)
  user_map          = { for i in local.user_indices : tostring(i) => i }
  user_location_map = { for i in local.user_indices : tostring(i) => var.locations[(i - 1) % local.region_count] }
}

module "entra" {
  source = "./modules/entra_user"

  n                                             = var.n
  domain                                        = var.entra_user_domain
  password                                      = var.entra_user_password
  group_name                                    = var.entra_user_group
  project_name                                  = var.project_name
  frontend_redirect_uri                         = var.frontend_redirect_uri
  frontend_additional_redirect_uris             = var.frontend_additional_redirect_uris
  frontend_additional_post_logout_redirect_uris = var.frontend_additional_post_logout_redirect_uris
}

module "user_seats" {
  for_each = local.user_map
  source   = "./modules/user_seat"

  user_index             = each.value
  location               = local.user_location_map[each.key]
  user_object_id         = module.entra.user_object_ids[each.key]
  project_name_prefix    = var.project_name
  tags                   = var.tags
  auth_mode              = var.auth_mode
  tenant_id              = module.entra.tenant_id
  backend_api_client_id  = module.entra.backend_api_client_ids[each.key]
  frontend_spa_client_id = module.entra.frontend_spa_client_ids[each.key]
  backend_api_scope      = module.entra.backend_api_scopes[each.key]

  postgres_location              = var.postgres_location
  postgres_admin_login           = var.postgres_admin_login
  postgres_admin_password        = var.postgres_admin_password
  postgres_sku                   = var.postgres_sku
  postgres_storage_mb            = var.postgres_storage_mb
  postgres_version               = var.postgres_version
  postgres_password_auth_enabled = var.postgres_password_auth_enabled
  client_ip                      = var.client_ip
  search_sku                     = var.search_sku
  search_location                = var.search_location
  cosmosdb_throughput            = var.cosmosdb_throughput
  redis_sku                      = var.redis_sku
  redis_family                   = var.redis_family
  redis_capacity                 = var.redis_capacity
}

module "all_users_subscription" {
  source = "./modules/all_users_subscription"

  subscription_id = var.subscription_id
  group_object_id = module.entra.group_object_id
}
