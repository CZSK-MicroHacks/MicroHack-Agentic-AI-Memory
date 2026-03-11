variable "user_index" {
  type        = number
  description = "Numeric seat index used for naming and user assignment."
}

variable "location" {
  type        = string
  description = "Azure region used for the seat resource group and most resources."
}

variable "user_object_id" {
  type        = string
  description = "Object ID of the Entra user that receives Owner on the seat resource group."
}

variable "project_name_prefix" {
  type        = string
  description = "Short alphanumeric prefix used when naming seat resources."
}

variable "tags" {
  type        = map(string)
  description = "Base tags applied to resources in the seat."
}

variable "auth_mode" {
  type        = string
  description = "Authentication mode injected into the frontend and backend apps."
}

variable "tenant_id" {
  type        = string
  description = "Entra tenant ID used by the deployed applications and PostgreSQL AAD authentication."
}

variable "backend_api_client_id" {
  type        = string
  description = "Client ID of the seat-specific backend API app registration."
}

variable "frontend_spa_client_id" {
  type        = string
  description = "Client ID of the seat-specific frontend SPA app registration."
}

variable "backend_api_scope" {
  type        = string
  description = "Fully qualified delegated scope exposed by the seat-specific backend API app registration."
}

variable "postgres_location" {
  type        = string
  description = "Optional override for PostgreSQL Flexible Server region; leave empty to use the seat region."
}

variable "postgres_admin_login" {
  type        = string
  description = "PostgreSQL administrator login."
}

variable "postgres_admin_password" {
  type        = string
  sensitive   = true
  description = "PostgreSQL administrator password."
}

variable "postgres_sku" {
  type        = string
  description = "SKU name for PostgreSQL Flexible Server."
}

variable "postgres_storage_mb" {
  type        = number
  description = "Storage size in MB for PostgreSQL Flexible Server."
}

variable "postgres_version" {
  type        = string
  description = "Major PostgreSQL version."
}

variable "postgres_password_auth_enabled" {
  type        = bool
  description = "Whether PostgreSQL password authentication remains enabled."
}

variable "client_ip" {
  type        = string
  description = "Optional client IP to allow through the PostgreSQL firewall."
}

variable "search_sku" {
  type        = string
  description = "Azure AI Search SKU."
}

variable "search_location" {
  type        = string
  description = "Optional override for Azure AI Search region; leave empty to use the seat region."
}

variable "cosmosdb_throughput" {
  type        = number
  description = "Cosmos DB provisioned throughput in RU/s."
}

variable "redis_sku" {
  type        = string
  description = "Azure Cache for Redis SKU."
}

variable "redis_family" {
  type        = string
  description = "Azure Cache for Redis family."
}

variable "redis_capacity" {
  type        = number
  description = "Azure Cache for Redis capacity."
}
