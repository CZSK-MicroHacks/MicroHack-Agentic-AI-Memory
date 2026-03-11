locals {
  padded                      = format("%03d", var.user_index)
  seat_name                   = "user${local.padded}"
  project_name                = lower("${var.project_name_prefix}${local.padded}")
  resource_group_name         = "rg-${var.project_name_prefix}-${local.padded}"
  effective_postgres_location = trimspace(var.postgres_location) != "" ? var.postgres_location : var.location
  effective_search_location   = trimspace(var.search_location) != "" ? var.search_location : var.location
  postgres_server_name        = "pgflex-${local.project_name}-db"
  seat_tags = merge(var.tags, {
    seat      = local.seat_name
    userIndex = local.padded
  })
}
