variable "subscription_id" {
  type        = string
  description = "Azure subscription ID where the provider-registration role is created and assigned."
}

variable "group_object_id" {
  type        = string
  description = "Object ID of the Entra group that should receive provider-registration permissions."
}
