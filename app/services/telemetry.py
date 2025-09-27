"""Model usage telemetry and cost tracking."""
from decimal import Decimal
from typing import Dict, Optional
from sqlalchemy.orm import Session
from .database import get_db
from .models import RunModelUsage


# Model cost rates per token (USD)
RATE_MAP = {
    "generic-primary": 0.0000015,
    "generic-fallback": 0.0000012,
}


def record_model_usage(
    run_id: str,
    node_key: str,
    usage_dict: Dict,
    db: Optional[Session] = None
) -> None:
    """Record model usage and estimated cost to database."""
    if db is None:
        db = next(get_db())
    
    provider = usage_dict.get("provider", "unknown")
    model_name = usage_dict.get("model_name", "unknown")
    prompt_tokens = usage_dict.get("prompt_tokens", 0)
    completion_tokens = usage_dict.get("completion_tokens", 0)
    total_tokens = prompt_tokens + completion_tokens
    
    # Calculate estimated cost
    rate = RATE_MAP.get(model_name, 0.0)
    estimated_cost = Decimal(str(total_tokens * rate))
    
    usage_record = RunModelUsage(
        run_id=run_id,
        node_key=node_key,
        provider=provider,
        model_name=model_name,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=str(estimated_cost)
    )
    
    db.add(usage_record)
    db.commit()