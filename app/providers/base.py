"""Base model provider interface and implementations."""
from abc import ABC, abstractmethod
from typing import Dict, Any
from dataclasses import dataclass


@dataclass
class ModelUsage:
    """Model usage metadata."""
    provider: str
    model_name: str
    prompt_tokens: int
    completion_tokens: int
    
    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class ModelProvider(ABC):
    """Base interface for model providers."""
    
    @abstractmethod
    async def generate(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate output from input data."""
        pass
    
    @abstractmethod
    def get_usage(self) -> ModelUsage:
        """Get usage metadata for the last generation."""
        pass


class PrimaryProvider(ModelProvider):
    """Primary model provider implementation."""
    
    def __init__(self):
        self.last_usage = None
        self._generation_count = 0
    
    async def generate(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate deterministic output for testing."""
        self._generation_count += 1
        
        # Simulate token usage
        input_length = len(str(input_data))
        prompt_tokens = max(50, input_length // 4)
        completion_tokens = max(30, prompt_tokens // 2)
        
        self.last_usage = ModelUsage(
            provider="primary",
            model_name="generic-primary",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens
        )
        
        # Return deterministic output
        return {
            "output": f"Primary response {self._generation_count}: Processed input successfully",
            "confidence": 0.95,
            "processing_time": 150
        }
    
    def get_usage(self) -> ModelUsage:
        """Get usage metadata."""
        return self.last_usage


class FallbackProvider(ModelProvider):
    """Fallback model provider implementation."""
    
    def __init__(self):
        self.last_usage = None
        self._generation_count = 0
    
    async def generate(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate deterministic fallback output."""
        self._generation_count += 1
        
        # Simulate different token usage patterns
        input_length = len(str(input_data))
        prompt_tokens = max(40, input_length // 5)
        completion_tokens = max(25, prompt_tokens // 3)
        
        self.last_usage = ModelUsage(
            provider="fallback",
            model_name="generic-fallback",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens
        )
        
        # Return fallback output
        return {
            "output": f"Fallback response {self._generation_count}: Safe default processing",
            "confidence": 0.75,
            "processing_time": 100
        }
    
    def get_usage(self) -> ModelUsage:
        """Get usage metadata."""
        return self.last_usage


class ProviderFactory:
    """Factory for creating model providers."""
    
    @staticmethod
    def get_primary_provider() -> ModelProvider:
        """Get primary model provider."""
        import os
        # Use mock provider for testing, OpenAI for production
        if os.getenv("USE_MOCK_PROVIDERS", "false").lower() == "true":
            return PrimaryProvider()
        else:
            from .openai_provider import OpenAIPrimaryProvider
            return OpenAIPrimaryProvider()
    
    @staticmethod
    def get_fallback_provider() -> ModelProvider:
        """Get fallback model provider."""
        import os
        # Use mock provider for testing, OpenAI for production
        if os.getenv("USE_MOCK_PROVIDERS", "false").lower() == "true":
            return FallbackProvider()
        else:
            from .openai_provider import OpenAIFallbackProvider
            return OpenAIFallbackProvider()