"""In-memory token bucket rate limiting implementation."""
import os
import time
import hashlib
from typing import Dict, Tuple
from fastapi import HTTPException, Request


class TokenBucket:
    """In-memory token bucket for rate limiting."""
    
    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.tokens = float(capacity)
        self.refill_rate = refill_rate  # tokens per second
        self.last_refill = time.time()
    
    def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens. Returns True if allowed, False if rate limited."""
        current_time = time.time()
        
        # Refill tokens based on time elapsed
        time_passed = current_time - self.last_refill
        self.tokens = min(self.capacity, self.tokens + time_passed * self.refill_rate)
        self.last_refill = current_time
        
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False


class InMemoryRateLimiter:
    """In-memory rate limiter using token buckets per subject."""
    
    def __init__(self):
        self.buckets: Dict[str, TokenBucket] = {}
        self.window_seconds = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
        self.max_requests = int(os.getenv("RATE_LIMIT_REQUESTS", "20"))
    
    def _get_bucket(self, subject: str) -> TokenBucket:
        """Get or create a token bucket for the subject."""
        if subject not in self.buckets:
            # Calculate refill rate: max_requests per window_seconds
            refill_rate = self.max_requests / self.window_seconds
            self.buckets[subject] = TokenBucket(self.max_requests, refill_rate)
        return self.buckets[subject]
    
    def is_allowed(self, subject: str) -> Tuple[bool, Dict[str, str]]:
        """Check if request is allowed for subject."""
        bucket = self._get_bucket(subject)
        allowed = bucket.consume(1)
        
        if not allowed:
            return False, {
                "detail": "Rate limit exceeded",
                "retry_after": str(self.window_seconds),
                "limit": str(self.max_requests),
                "window": f"{self.window_seconds}s"
            }
        
        return True, {}
    
    def cleanup_old_buckets(self):
        """Clean up old unused buckets (basic cleanup)."""
        current_time = time.time()
        cleanup_threshold = 3600  # 1 hour
        
        to_remove = []
        for subject, bucket in self.buckets.items():
            if current_time - bucket.last_refill > cleanup_threshold:
                to_remove.append(subject)
        
        for subject in to_remove:
            del self.buckets[subject]


# Global rate limiter instance
rate_limiter = InMemoryRateLimiter()


def get_rate_limit_subject(request: Request, token: str = None) -> str:
    """Generate rate limit subject from request (token hash)."""
    if token:
        # Hash token for privacy
        return hashlib.sha256(token.encode()).hexdigest()[:16]
    
    # Fallback to IP address if no token
    client_ip = request.client.host if request.client else "unknown"
    return f"ip_{client_ip}"


def check_rate_limit(request: Request, token: str = None) -> None:
    """Check rate limit for request. Raises HTTPException if exceeded."""
    subject = get_rate_limit_subject(request, token)
    allowed, error_data = rate_limiter.is_allowed(subject)
    
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=error_data
        )