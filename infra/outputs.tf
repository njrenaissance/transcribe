output "speech_endpoint" {
  description = "Endpoint for the Azure Speech resource. Feeds AZURE_SPEECH_ENDPOINT."
  value       = azurerm_cognitive_account.speech.endpoint
}

output "speech_primary_key" {
  description = "Primary API key for the Azure Speech resource. Feeds AZURE_SPEECH_KEY."
  value       = azurerm_cognitive_account.speech.primary_access_key
  sensitive   = true
}
