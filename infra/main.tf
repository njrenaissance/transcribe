resource "azurerm_resource_group" "transcribe" {
  name     = var.resource_group_name
  location = var.location
  tags     = var.tags
}

resource "azurerm_cognitive_account" "speech" {
  name                = var.speech_account_name
  resource_group_name = azurerm_resource_group.transcribe.name
  location            = azurerm_resource_group.transcribe.location
  kind                = "SpeechServices"
  sku_name            = var.sku_name
  tags                = var.tags
}
