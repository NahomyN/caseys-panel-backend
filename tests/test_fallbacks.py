import pytest
from app.agents.base import BaseAgent, TransientAgentError, PermanentAgentError
from app.schemas.base import AgentInput, AgentOutput

class FlakyAgent(BaseAgent):
    def __init__(self):
        super().__init__(50, "Flaky")
        self.calls = 0
    async def process(self, input_data: AgentInput) -> AgentOutput:
        self.calls += 1
        raise TransientAgentError("Simulated transient error")
    async def fallback_process(self, input_data: AgentInput, error: Exception):  # type: ignore[override]
        return AgentOutput(agent_no=50, content_md="# Fallback Output")

class BadAgent(BaseAgent):
    def __init__(self):
        super().__init__(51, "Bad")
        self.calls = 0
    async def process(self, input_data: AgentInput) -> AgentOutput:
        self.calls += 1
        raise PermanentAgentError("Schema violation")
    async def fallback_process(self, input_data: AgentInput, error: Exception):  # type: ignore[override]
        return AgentOutput(agent_no=51, content_md="# Fallback Minimal")

@pytest.mark.asyncio
async def test_transient_retry_then_fallback():
    agent = FlakyAgent()
    inp = AgentInput(patient_id="p", raw_text_refs=["r"])
    out = await agent.run_with_retry(inp)
    assert out.content_md.startswith("# Fallback")
    assert agent.calls == agent.max_retries  # exhausted retries

@pytest.mark.asyncio
async def test_permanent_immediate_fallback():
    agent = BadAgent()
    inp = AgentInput(patient_id="p", raw_text_refs=["r"])
    out = await agent.run_with_retry(inp)
    assert out.content_md.startswith("# Fallback")
    # Permanent error should not retry full cycle; ensure < max_retries attempts
    assert agent.calls == 1
