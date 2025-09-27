from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import asyncio
import logging
import time
from ..schemas.base import AgentInput, AgentOutput, EventType
from ..services import checkpointer as checkpointer_module


class TransientAgentError(Exception):
    """Retryable issues: network timeouts, rate limits, temporary model errors."""


class PermanentAgentError(Exception):
    """Non-retryable issues: validation logic, unsupported input, business rule violation."""


class FallbackExhaustedError(Exception):
    """Raised when fallback also fails or returns None when mandatory output required."""

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    def __init__(self, agent_no: int, name: str):
        self.agent_no = agent_no
        self.name = name
        self.max_retries = 4
        self.retry_delays = [1, 2, 4, 8]
    
    @abstractmethod
    async def process(self, input_data: AgentInput) -> AgentOutput:
        pass
    
    async def run_with_retry(self, input_data: AgentInput) -> AgentOutput:
        last_error = None
        start_time = time.perf_counter()
        attempts = 0
        
        for attempt in range(self.max_retries):
            attempts = attempt + 1
            try:
                logger.info(f"Agent {self.agent_no} attempt {attempts}")
                result = await self.process(input_data)
                # Synthetic model usage metrics placeholder (to be replaced with real provider data)
                if not hasattr(result, 'flags'):
                    result.flags = {}
                usage = result.flags.setdefault("model_usage", {})
                # Only populate if not already set by concrete agent
                if not usage.get("prompt_tokens"):
                    usage.update({
                        "provider": "mock-provider",
                        "model": "mock-model-v1",
                        "prompt_tokens": 100,
                        "completion_tokens": 200,
                        "estimated_cost_usd": "0.0012"
                    })
                logger.info(f"Agent {self.agent_no} succeeded on attempt {attempts}")
                duration_ms = (time.perf_counter() - start_time) * 1000
                # Attach metrics to flags (non-PHI)
                result.flags.setdefault("metrics", {})
                result.flags["metrics"].update({
                    "attempts": attempts,
                    "retries": attempts - 1,
                    "duration_ms": round(duration_ms, 2),
                    "fallback_used": False
                })
                return result
            except Exception as e:
                last_error = e
                retryable = isinstance(e, TransientAgentError) or not isinstance(e, PermanentAgentError)
                logger.warning(f"Agent {self.agent_no} failed attempt {attempts}: {str(e)} | retryable={retryable}")
                if attempt < self.max_retries - 1 and retryable:
                    delay = self.retry_delays[attempt]
                    logger.info(f"Agent {self.agent_no} retrying in {delay}s")
                    # Emit RETRIED event
                    try:
                        checkpointer_module.checkpointer.save_event(
                            getattr(input_data, 'run_id', 'unknown'),
                            f"agent_{self.agent_no}",
                            EventType.RETRIED,
                            {"attempt": attempts, "error": str(e)}
                        )
                    except Exception:
                        logger.debug("Retry event emission failed silently")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"Agent {self.agent_no} terminating retries (attempt {attempts})")
                    break

        # Attempt fallback once if defined
        try:
            fb = await self.fallback_process(input_data, last_error)  # type: ignore[arg-type]
            if fb is not None:
                # Emit RETRIED event with fallback indication only if fallback succeeded
                try:
                    checkpointer_module.checkpointer.save_event(
                        getattr(input_data, 'run_id', 'unknown'),
                        f"agent_{self.agent_no}",
                        EventType.RETRIED,
                        {"fallback": True, "final_retry_attempts": attempts, "error": str(last_error)}
                    )
                except Exception:
                    logger.debug("Fallback retry event emission failed silently")
                    
                logger.info(f"Agent {self.agent_no} fallback succeeded after {attempts} primary attempts")
                duration_ms = (time.perf_counter() - start_time) * 1000
                fb.flags.setdefault("metrics", {})
                fb.flags["metrics"].update({
                    "attempts": attempts,
                    "retries": attempts - 1,
                    "duration_ms": round(duration_ms, 2),
                    "fallback_used": True
                })
                # Fallback model usage (synthetic)
                fu = fb.flags.setdefault("model_usage", {})
                if not fu.get("prompt_tokens"):
                    fu.update({
                        "provider": "mock-provider",
                        "model": "mock-model-fallback",
                        "prompt_tokens": 50,
                        "completion_tokens": 120,
                        "estimated_cost_usd": "0.0007"
                    })
                return fb
        except Exception as fe:
            logger.error(f"Agent {self.agent_no} fallback failed: {fe}")
            raise FallbackExhaustedError(str(fe)) from fe

        if last_error:
            raise last_error  # propagate original
        raise Exception(f"Agent {self.agent_no} failed after all retries")
    
    async def fallback_process(self, input_data: AgentInput, error: Exception) -> Optional[AgentOutput]:
        logger.warning(f"Agent {self.agent_no} fallback triggered due to: {str(error)}")
        return None