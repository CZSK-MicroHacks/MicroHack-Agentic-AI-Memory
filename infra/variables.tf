# -----------------------------------------------------------------------------
# Core Variables
# -----------------------------------------------------------------------------

variable "subscription_id" {
  description = "Azure subscription ID"
  type        = string
}

variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
  default     = "rg-mh-ai-memory"
}

variable "location" {
  description = "Azure region for all resources"
  type        = string
  default     = "eastus2"
}

variable "project_name" {
  description = "Short project name used as naming prefix"
  type        = string
  default     = "mhaimem"
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default = {
    project     = "ag-ui-demo"
    environment = "dev"
    managedBy   = "terraform"
  }
}

# -----------------------------------------------------------------------------
# Entra ID Authentication
# -----------------------------------------------------------------------------

variable "auth_mode" {
  description = "Authentication mode for deployed applications (entra or mock)."
  type        = string
  default     = "entra"

  validation {
    condition     = contains(["entra", "mock"], lower(var.auth_mode))
    error_message = "auth_mode must be either 'entra' or 'mock'."
  }
}

variable "frontend_additional_redirect_uris" {
  description = "Additional redirect URIs for the frontend SPA app registration."
  type        = list(string)
  default     = []
}

variable "frontend_redirect_uri" {
  description = "Primary frontend redirect URI for Entra SPA registration (e.g. ACA frontend FQDN)."
  type        = string
  default     = ""
}

variable "frontend_additional_post_logout_redirect_uris" {
  description = "Additional post-logout redirect URIs for the frontend SPA app registration."
  type        = list(string)
  default     = []
}

# -----------------------------------------------------------------------------
# PostgreSQL
# -----------------------------------------------------------------------------

variable "postgres_location" {
  description = "Azure region for PostgreSQL (if restricted in primary location)"
  type        = string
  default     = "westus2"
}

variable "postgres_admin_login" {
  description = "PostgreSQL administrator login"
  type        = string
  default     = "pgadmin"
}

variable "postgres_admin_password" {
  description = "PostgreSQL administrator password"
  type        = string
  sensitive   = true
}

variable "postgres_sku" {
  description = "PostgreSQL Flexible Server SKU"
  type        = string
  default     = "B_Standard_B1ms"
}

variable "postgres_storage_mb" {
  description = "PostgreSQL storage in MB"
  type        = number
  default     = 32768
}

variable "postgres_version" {
  description = "PostgreSQL major version"
  type        = string
  default     = "16"
}

variable "postgres_password_auth_enabled" {
  description = "Whether PostgreSQL password authentication remains enabled (set false after managed identity cutover)."
  type        = bool
  default     = true
}

variable "client_ip" {
  description = "Client IP address to allow through the PostgreSQL firewall for development access."
  type        = string
  default     = ""
}



# -----------------------------------------------------------------------------
# Azure AI Search
# -----------------------------------------------------------------------------

variable "search_sku" {
  description = "Azure AI Search SKU (standard required for semantic ranker / agentic retrieval)"
  type        = string
  default     = "standard"
}

variable "search_location" {
  description = "Azure region for AI Search (may differ from primary location due to capacity)"
  type        = string
  default     = "westus2"
}

# -----------------------------------------------------------------------------
# Cosmos DB
# -----------------------------------------------------------------------------

variable "cosmosdb_throughput" {
  description = "Cosmos DB provisioned throughput (RU/s)"
  type        = number
  default     = 400
}

# -----------------------------------------------------------------------------
# Redis
# -----------------------------------------------------------------------------

variable "redis_sku" {
  description = "Redis Cache SKU name"
  type        = string
  default     = "Basic"
}

variable "redis_family" {
  description = "Redis Cache family"
  type        = string
  default     = "C"
}

variable "redis_capacity" {
  description = "Redis Cache capacity (size)"
  type        = number
  default     = 0
}
