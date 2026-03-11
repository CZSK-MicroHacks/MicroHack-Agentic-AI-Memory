variable "n" {
  type        = number
  default     = 4
  description = <<EOT
Number of student seats to provision.
Each seat creates its own resource group and a full copy of the Azure application stack through the user_seat module.
EOT

  validation {
    condition     = var.n >= 1
    error_message = "n must be at least 1."
  }
}

variable "entra_user_domain" {
  type        = string
  default     = "tkubica.net"
  description = <<EOT
Domain appended to generated Entra user principal names.
Users are created as userNNN@domain, for example user001@tkubica.net.
EOT
}

variable "entra_user_password" {
  type        = string
  sensitive   = true
  default     = ""
  description = <<EOT
Password assigned to all generated Entra users for the workshop.
Set this through TF_VAR_entra_user_password or a non-committed tfvars file before apply.
EOT
}

variable "entra_user_group" {
  type        = string
  default     = "microhack-users"
  description = "Display name of the Entra group that contains all workshop users."
}

variable "subscription_id" {
  type        = string
  description = <<EOT
Azure subscription ID used for all seat deployments and subscription-level RBAC.
Provide this through tfvars, CLI input, or TF_VAR_subscription_id.
EOT
}

variable "locations" {
  type        = list(string)
  description = <<EOT
List of Azure regions used for seat placement.
Seats are distributed across the list in round-robin order.
EOT

  validation {
    condition     = length(var.locations) > 0 && alltrue([for location in var.locations : length(trimspace(location)) > 0])
    error_message = "Provide at least one non-empty Azure region in locations."
  }
}

variable "project_name" {
  type        = string
  default     = "mhaimem"
  description = "Short alphanumeric prefix used when naming per-seat Azure resources."
}

variable "tags" {
  type        = map(string)
  description = "Base tags applied to all seat resources."
  default = {
    project     = "ag-ui-demo"
    environment = "dev"
    managedBy   = "terraform"
  }
}

variable "auth_mode" {
  type        = string
  default     = "entra"
  description = "Authentication mode injected into each deployed frontend and backend application."

  validation {
    condition     = contains(["entra", "mock"], lower(var.auth_mode))
    error_message = "auth_mode must be either 'entra' or 'mock'."
  }
}

variable "frontend_redirect_uri" {
  type        = string
  default     = ""
  description = <<EOT
Primary redirect URI for the shared frontend SPA registration.
Use this to add a known frontend URL in addition to localhost before or after deployment.
EOT
}

variable "frontend_additional_redirect_uris" {
  type        = list(string)
  default     = []
  description = "Additional redirect URIs for the shared frontend SPA app registration."
}

variable "frontend_additional_post_logout_redirect_uris" {
  type        = list(string)
  default     = []
  description = "Additional post-logout redirect URIs for the shared frontend SPA app registration."
}

variable "postgres_location" {
  type        = string
  default     = ""
  description = "Optional override for PostgreSQL Flexible Server region; leave empty to use the seat's configured seat region."
}

variable "postgres_admin_login" {
  type        = string
  default     = "pgadmin"
  description = "Administrator login name for each seat's PostgreSQL Flexible Server."
}

variable "postgres_admin_password" {
  type        = string
  sensitive   = true
  description = "Administrator password for each seat's PostgreSQL Flexible Server."
}

variable "postgres_sku" {
  type        = string
  default     = "B_Standard_B1ms"
  description = "SKU name for each seat's PostgreSQL Flexible Server."
}

variable "postgres_storage_mb" {
  type        = number
  default     = 32768
  description = "Allocated storage size in MB for each seat's PostgreSQL Flexible Server."
}

variable "postgres_version" {
  type        = string
  default     = "16"
  description = "Major PostgreSQL version used for each seat."
}

variable "postgres_password_auth_enabled" {
  type        = bool
  default     = true
  description = "Whether password authentication remains enabled on each seat's PostgreSQL server."
}

variable "client_ip" {
  type        = string
  default     = ""
  description = "Optional client IP allowed through the PostgreSQL firewall for direct development access."
}

variable "search_sku" {
  type        = string
  default     = "standard"
  description = "Azure AI Search SKU used for each seat deployment."
}

variable "search_location" {
  type        = string
  default     = ""
  description = "Optional override for Azure AI Search region; leave empty to use the seat's configured seat region."
}

variable "cosmosdb_throughput" {
  type        = number
  default     = 400
  description = "Provisioned Cosmos DB throughput in RU/s for each seat."
}

variable "redis_sku" {
  type        = string
  default     = "Basic"
  description = "Azure Cache for Redis SKU used for each seat."
}

variable "redis_family" {
  type        = string
  default     = "C"
  description = "Azure Cache for Redis family used for each seat."
}

variable "redis_capacity" {
  type        = number
  default     = 0
  description = "Azure Cache for Redis capacity for each seat."
}
