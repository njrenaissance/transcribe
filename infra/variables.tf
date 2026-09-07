variable "resource_group_name" {
  description = "Name of the Azure resource group to create for the Speech resource."
  type        = string
  default     = "transcribe-rg"
}

variable "location" {
  description = "Azure region to deploy the Speech resource into."
  type        = string
  default     = "eastus"
}

variable "speech_account_name" {
  description = "Name of the Azure Cognitive Services Speech resource. Must be globally unique."
  type        = string
  default     = "transcribe-speech"
}

variable "sku_name" {
  description = "Pricing tier for the Speech resource (e.g. F0 for free tier, S0 for standard)."
  type        = string
  default     = "S0"
}

variable "tags" {
  description = "Tags applied to all resources created by this configuration."
  type        = map(string)
  default     = {}
}
