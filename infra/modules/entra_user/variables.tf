variable "n" {
  type        = number
  description = "Number of workshop users to create."
}

variable "domain" {
  type        = string
  description = "Domain appended to generated workshop user UPNs."
}

variable "password" {
  type        = string
  sensitive   = true
  description = "Password assigned to all generated workshop users."
}

variable "group_name" {
  type        = string
  description = "Display name for the Entra security group containing all workshop users."
}

variable "project_name" {
  type        = string
  description = "Project name prefix used when naming per-seat Entra app registrations."
}

variable "frontend_redirect_uri" {
  type        = string
  default     = ""
  description = "Primary redirect URI added to each seat-specific frontend SPA application."
}

variable "frontend_additional_redirect_uris" {
  type        = list(string)
  default     = []
  description = "Additional redirect URIs added to each seat-specific frontend SPA application."
}

variable "frontend_additional_post_logout_redirect_uris" {
  type        = list(string)
  default     = []
  description = "Additional post-logout redirect URIs added to each seat-specific frontend SPA application."
}
