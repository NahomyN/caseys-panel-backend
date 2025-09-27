"""Azure Key Vault integration for secure secret management."""

import os
import logging
from typing import Optional, Dict, Any
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
from azure.core.exceptions import AzureError

logger = logging.getLogger(__name__)


class AzureSecretsManager:
    """Manages secrets using Azure Key Vault with managed identity."""

    def __init__(self):
        self.vault_url = os.getenv("AZURE_KEY_VAULT_URL")
        self.client: Optional[SecretClient] = None
        self._secrets_cache: Dict[str, str] = {}
        self._initialize_client()

    def _initialize_client(self):
        """Initialize the Key Vault client with appropriate credentials."""
        if not self.vault_url:
            logger.warning("AZURE_KEY_VAULT_URL not set, falling back to environment variables")
            return

        try:
            # Try managed identity first (for Azure App Service)
            if os.getenv("MSI_ENDPOINT"):
                credential = ManagedIdentityCredential()
                logger.info("Using managed identity for Key Vault authentication")
            else:
                # Fall back to default credential chain for local development
                credential = DefaultAzureCredential()
                logger.info("Using default credential chain for Key Vault authentication")

            self.client = SecretClient(vault_url=self.vault_url, credential=credential)

            # Test connection
            self._test_connection()
            logger.info(f"Successfully connected to Key Vault: {self.vault_url}")

        except Exception as e:
            logger.error(f"Failed to initialize Key Vault client: {str(e)}")
            self.client = None

    def _test_connection(self):
        """Test Key Vault connection by attempting to list secrets."""
        if self.client:
            try:
                # Just check if we can connect, don't actually list all secrets
                list(self.client.list_properties_of_secrets(max_page_size=1))
            except AzureError as e:
                logger.warning(f"Key Vault connection test failed: {str(e)}")
                raise

    def get_secret(self, secret_name: str, default: Optional[str] = None) -> Optional[str]:
        """Get a secret from Azure Key Vault with fallback to environment variables."""
        # Check cache first
        if secret_name in self._secrets_cache:
            return self._secrets_cache[secret_name]

        # Try Key Vault if available
        if self.client:
            try:
                secret = self.client.get_secret(secret_name)
                value = secret.value
                # Cache the secret
                self._secrets_cache[secret_name] = value
                logger.debug(f"Retrieved secret '{secret_name}' from Key Vault")
                return value

            except AzureError as e:
                logger.warning(f"Failed to retrieve secret '{secret_name}' from Key Vault: {str(e)}")

        # Fallback to environment variable
        env_value = os.getenv(secret_name.upper().replace("-", "_"), default)
        if env_value:
            logger.debug(f"Retrieved secret '{secret_name}' from environment variable")
            self._secrets_cache[secret_name] = env_value
            return env_value

        logger.warning(f"Secret '{secret_name}' not found in Key Vault or environment variables")
        return default

    def set_secret(self, secret_name: str, secret_value: str) -> bool:
        """Set a secret in Azure Key Vault."""
        if not self.client:
            logger.error("Key Vault client not available for setting secrets")
            return False

        try:
            self.client.set_secret(secret_name, secret_value)
            # Update cache
            self._secrets_cache[secret_name] = secret_value
            logger.info(f"Successfully set secret '{secret_name}' in Key Vault")
            return True

        except AzureError as e:
            logger.error(f"Failed to set secret '{secret_name}' in Key Vault: {str(e)}")
            return False

    def refresh_secret(self, secret_name: str) -> Optional[str]:
        """Refresh a secret from Key Vault, bypassing cache."""
        if secret_name in self._secrets_cache:
            del self._secrets_cache[secret_name]

        return self.get_secret(secret_name)

    def get_api_keys(self) -> Dict[str, Optional[str]]:
        """Get all API keys needed for the application."""
        api_keys = {
            "openai_api_key": self.get_secret("openai-api-key"),
            "anthropic_api_key": self.get_secret("anthropic-api-key"),
            "azure_openai_key": self.get_secret("azure-openai-key"),
            "azure_openai_endpoint": self.get_secret("azure-openai-endpoint"),
        }

        # Log which keys were found (without exposing values)
        found_keys = [k for k, v in api_keys.items() if v]
        missing_keys = [k for k, v in api_keys.items() if not v]

        if found_keys:
            logger.info(f"Successfully retrieved API keys: {', '.join(found_keys)}")
        if missing_keys:
            logger.warning(f"Missing API keys: {', '.join(missing_keys)}")

        return api_keys

    def health_check(self) -> Dict[str, Any]:
        """Health check for Key Vault connectivity."""
        if not self.vault_url:
            return {
                "status": "disabled",
                "message": "Key Vault URL not configured",
                "vault_url": None
            }

        if not self.client:
            return {
                "status": "error",
                "message": "Key Vault client not initialized",
                "vault_url": self.vault_url
            }

        try:
            # Test connection
            list(self.client.list_properties_of_secrets(max_page_size=1))
            return {
                "status": "healthy",
                "message": "Key Vault connection successful",
                "vault_url": self.vault_url,
                "cached_secrets": len(self._secrets_cache)
            }

        except AzureError as e:
            return {
                "status": "error",
                "message": f"Key Vault connection failed: {str(e)}",
                "vault_url": self.vault_url
            }


# Global instance
secrets_manager = AzureSecretsManager()


def get_secret(secret_name: str, default: Optional[str] = None) -> Optional[str]:
    """Convenience function to get a secret."""
    return secrets_manager.get_secret(secret_name, default)


def get_api_keys() -> Dict[str, Optional[str]]:
    """Convenience function to get all API keys."""
    return secrets_manager.get_api_keys()


def health_check() -> Dict[str, Any]:
    """Convenience function for health check."""
    return secrets_manager.health_check()