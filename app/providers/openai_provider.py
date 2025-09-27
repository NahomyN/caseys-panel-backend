"""OpenAI model provider implementation."""
import os
import logging
from typing import Dict, Any, Optional
import openai
from openai import AsyncOpenAI
from .base import ModelProvider, ModelUsage
from ..middleware.phi import scrub_phi_text

logger = logging.getLogger(__name__)


class OpenAIProvider(ModelProvider):
    """OpenAI model provider implementation."""
    
    def __init__(self, model_name: str = "gpt-4o-mini"):
        self.model_name = model_name
        self.client = None
        self.last_usage = None
        # Don't initialize client in constructor - do it lazily
    
    def _ensure_client(self):
        """Initialize OpenAI client if not already done.
        Supports Azure OpenAI when OPENAI_BASE_URL is provided (expects api-version).
        """
        if self.client is None:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable is required")
            base_url = os.getenv("OPENAI_BASE_URL")  # e.g., https://<resource>.openai.azure.com
            try:
                if base_url:
                    self.client = AsyncOpenAI(
                        api_key=api_key,
                        base_url=base_url,
                        timeout=30.0
                    )
                else:
                    self.client = AsyncOpenAI(
                        api_key=api_key,
                        timeout=30.0
                    )
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")
                raise ValueError(f"Failed to initialize OpenAI client: {e}")
    
    async def generate(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate output using OpenAI API."""
        self._ensure_client()
        
        try:
            # Extract and scrub the prompt
            prompt = self._extract_prompt(input_data)
            # Enforce minimal PHI: optionally block outbound PHI unless explicitly allowed
            allow_phi_external = os.getenv("PHI_ALLOWED_EXTERNAL", "false").lower() in {"1","true","yes"}
            if not allow_phi_external:
                prompt = scrub_phi_text(prompt)
            
            # Make API call to OpenAI
            extra_query = None
            api_version = os.getenv("OPENAI_API_VERSION")
            if api_version:
                extra_query = {"api-version": api_version}

            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "You are a medical AI assistant helping with clinical documentation."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,  # Low temperature for consistent medical output
                max_tokens=1000,
                top_p=0.9,
                extra_query=extra_query
            )
            
            # Extract response content
            output_text = response.choices[0].message.content
            
            # Record usage
            usage = response.usage
            self.last_usage = ModelUsage(
                provider="openai",
                model_name=self.model_name,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens
            )
            
            logger.info(f"OpenAI API call successful - Model: {self.model_name}, "
                       f"Tokens: {usage.prompt_tokens}+{usage.completion_tokens}")
            
            return {
                "output": output_text,
                "confidence": 0.95,  # OpenAI doesn't provide confidence scores
                "processing_time": 0,  # We don't track this currently
                "model_name": self.model_name,
                "finish_reason": response.choices[0].finish_reason
            }
            
        except openai.RateLimitError as e:
            logger.warning(f"OpenAI rate limit hit: {e}")
            raise Exception(f"Rate limit exceeded: {e}")
        except openai.APIError as e:
            logger.error(f"OpenAI API error: {e}")
            raise Exception(f"API error: {e}")
        except Exception as e:
            logger.error(f"OpenAI provider error: {e}")
            raise Exception(f"Provider error: {e}")
    
    def _extract_prompt(self, input_data: Dict[str, Any]) -> str:
        """Extract prompt text from input data."""
        # Handle different input formats
        if isinstance(input_data, str):
            return input_data
        elif isinstance(input_data, dict):
            # Look for common prompt keys
            prompt_keys = ['prompt', 'text', 'input', 'content', 'message']
            for key in prompt_keys:
                if key in input_data:
                    return str(input_data[key])
            # If no specific key found, convert the whole dict to string
            return str(input_data)
        else:
            return str(input_data)
    
    def get_usage(self) -> Optional[ModelUsage]:
        """Get usage metadata for the last generation."""
        return self.last_usage


class OpenAIPrimaryProvider(OpenAIProvider):
    """Primary OpenAI provider using the configured primary model."""
    
    def __init__(self):
        model = os.getenv("MODEL_PRIMARY", "gpt-4o-mini")
        super().__init__(model_name=model)


class OpenAIFallbackProvider(OpenAIProvider):
    """Fallback OpenAI provider using the configured fallback model."""
    
    def __init__(self):
        model = os.getenv("MODEL_FALLBACK", "gpt-3.5-turbo")
        super().__init__(model_name=model)