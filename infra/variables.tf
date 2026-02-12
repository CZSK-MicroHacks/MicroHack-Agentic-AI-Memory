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
