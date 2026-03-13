variable "subscription_id" {
  type        = string
  description = "Azure subscription ID where subscription-scope workshop roles are assigned."
}

variable "group_object_id" {
  type        = string
  description = "Object ID of the Entra group that should receive subscription-scope workshop permissions."
}
