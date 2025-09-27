"""Test rate limiting enforcement."""
import pytest
import time
from fastapi.testclient import TestClient
from app.main import app
from app.auth.security import generate_test_token
from app.services.rate_limiting import rate_limiter


client = TestClient(app)


def test_rate_limit_enforced():
    """Test that rate limiting is enforced after exceeding limit."""
    # Clear any existing buckets
    rate_limiter.buckets.clear()
    
    # Create token
    token = generate_test_token(["attending"])
    headers = {"Authorization": f"Bearer {token}"}
    
    # Get configured limits (default 20 requests per 60 seconds)
    max_requests = rate_limiter.max_requests
    
    # Make requests up to the limit
    successful_requests = 0
    for i in range(max_requests + 5):  # Try 5 more than limit
        response = client.post("/api/v1/workflows/rate_limit_test/start", headers=headers)
        
        if response.status_code != 429:
            successful_requests += 1
        else:
            # Should get 429 after hitting limit
            assert response.status_code == 429
            error_data = response.json()
            assert "Rate limit exceeded" in str(error_data)
            break
    
    # Should have made exactly max_requests successful requests
    assert successful_requests == max_requests, f"Expected {max_requests} successful requests, got {successful_requests}"
    
    # Next request should definitely be rate limited
    response = client.post("/api/v1/workflows/rate_limit_test2/start", headers=headers)
    assert response.status_code == 429, "Should be rate limited"
    
    print(f"✅ Rate limiting enforced after {max_requests} requests")


def test_rate_limit_different_tokens():
    """Test that rate limiting is per-token (different tokens have separate limits)."""
    # Clear buckets
    rate_limiter.buckets.clear()
    
    # Create different tokens
    token1 = generate_test_token(["attending"])
    token2 = generate_test_token(["resident"])
    
    headers1 = {"Authorization": f"Bearer {token1}"}
    headers2 = {"Authorization": f"Bearer {token2}"}
    
    # Exhaust limit for token1
    max_requests = rate_limiter.max_requests
    for i in range(max_requests):
        response = client.post(f"/api/v1/workflows/token1_test_{i}/start", headers=headers1)
        if response.status_code == 429:
            break
    
    # token1 should now be rate limited
    response = client.post("/api/v1/workflows/token1_final/start", headers=headers1)
    assert response.status_code == 429, "Token1 should be rate limited"
    
    # token2 should still work
    response = client.post("/api/v1/workflows/token2_test/start", headers=headers2)
    assert response.status_code != 429, "Token2 should not be rate limited"
    
    print("✅ Rate limiting is per-token")


def test_rate_limit_canvas_endpoints():
    """Test that rate limiting also applies to canvas endpoints."""
    # Clear buckets
    rate_limiter.buckets.clear()
    
    token = generate_test_token(["attending"])
    headers = {"Authorization": f"Bearer {token}"}
    
    canvas_data = {
        "content_md": "Test content",
        "version": 1,
        "content_json": {"test": "data"}
    }
    
    # Make many canvas update requests
    max_requests = rate_limiter.max_requests
    successful_requests = 0
    
    for i in range(max_requests + 2):
        response = client.post(f"/api/v1/canvases/rate_test_{i}/1", json=canvas_data, headers=headers)
        
        if response.status_code != 429:
            successful_requests += 1
        else:
            assert response.status_code == 429
            break
    
    assert successful_requests == max_requests, "Canvas endpoints should also be rate limited"
    
    print("✅ Rate limiting applies to canvas endpoints")


def test_rate_limit_response_format():
    """Test that rate limit response has correct format."""
    # Clear buckets
    rate_limiter.buckets.clear()
    
    token = generate_test_token(["attending"])
    headers = {"Authorization": f"Bearer {token}"}
    
    # Exhaust rate limit
    max_requests = rate_limiter.max_requests
    for i in range(max_requests + 1):
        response = client.post(f"/api/v1/workflows/format_test_{i}/start", headers=headers)
        if response.status_code == 429:
            break
    
    # Check the rate limit response format
    response = client.post("/api/v1/workflows/format_final/start", headers=headers)
    assert response.status_code == 429
    
    data = response.json()
    assert "detail" in data
    assert "Rate limit exceeded" in data["detail"]["detail"]
    
    # Should contain rate limit info
    assert "retry_after" in data["detail"]
    assert "limit" in data["detail"]
    assert "window" in data["detail"]
    
    print("✅ Rate limit response format correct")


def test_rate_limit_token_bucket_refill():
    """Test that token bucket refills over time."""
    # Clear buckets
    rate_limiter.buckets.clear()
    
    from app.services.rate_limiting import TokenBucket
    
    # Create a bucket with fast refill for testing (5 tokens, 2 per second)
    bucket = TokenBucket(5, 2.0)  
    
    # Consume all tokens
    for _ in range(5):
        assert bucket.consume() == True
    
    # Should be empty now
    assert bucket.consume() == False
    
    # Wait a bit and tokens should refill
    time.sleep(1.5)  # Should refill ~3 tokens
    
    # Should be able to consume some tokens now
    assert bucket.consume() == True
    assert bucket.consume() == True
    assert bucket.consume() == True
    
    # But not too many
    assert bucket.consume() == False
    
    print("✅ Token bucket refills over time")


def test_rate_limit_subject_hashing():
    """Test that token subjects are properly hashed for privacy."""
    from app.services.rate_limiting import get_rate_limit_subject
    from unittest.mock import MagicMock
    
    # Mock request
    request = MagicMock()
    request.client.host = "127.0.0.1"
    
    # Test with token
    token = "test_token_123"
    subject = get_rate_limit_subject(request, token)
    
    # Should be a hash, not the original token
    assert subject != token
    assert len(subject) == 16  # SHA256 truncated to 16 chars
    
    # Same token should produce same subject
    subject2 = get_rate_limit_subject(request, token)
    assert subject == subject2
    
    # Different tokens should produce different subjects
    subject3 = get_rate_limit_subject(request, "different_token")
    assert subject != subject3
    
    # Without token, should use IP
    subject_ip = get_rate_limit_subject(request, None)
    assert subject_ip.startswith("ip_")
    
    print("✅ Rate limit subjects properly hashed")


if __name__ == "__main__":
    test_rate_limit_enforced()
    test_rate_limit_different_tokens()
    test_rate_limit_canvas_endpoints()
    test_rate_limit_response_format()
    test_rate_limit_token_bucket_refill()
    test_rate_limit_subject_hashing()