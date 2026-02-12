# -----------------------------------------------------------------------------
# Azure Cache for Redis
# -----------------------------------------------------------------------------

resource "azurerm_redis_cache" "main" {
  name                          = "redis-${var.project_name}"
  resource_group_name           = azurerm_resource_group.main.name
  location                      = azurerm_resource_group.main.location
  capacity                      = var.redis_capacity
  family                        = var.redis_family
  sku_name                      = var.redis_sku
  non_ssl_port_enabled          = false
  minimum_tls_version           = "1.2"
  public_network_access_enabled = true

  redis_configuration {}

  tags = var.tags
}
