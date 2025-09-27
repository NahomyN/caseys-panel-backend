import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.auth.security import generate_test_token
from app.services.database import SessionLocal, engine
from app.services.models import Base


client = TestClient(app)


def test_jwt_auth_enforcement():
    """Test JWT authentication enforcement on protected endpoints."""
    # Ensure tables exist
    Base.metadata.create_all(bind=engine)
    
    patient_id = "test_patient_auth"
    
    # Test 1: Missing Authorization header should return 401 or 403
    response = client.post(f"/api/v1/workflows/{patient_id}/start")
    assert response.status_code in [401, 403]  # FastAPI HTTPBearer may return either
    
    # Test 2: Invalid token should return 401
    invalid_headers = {"Authorization": "Bearer invalid_token_here"}
    response = client.post(f"/api/v1/workflows/{patient_id}/start", headers=invalid_headers)
    assert response.status_code == 401
    assert "Invalid token" in response.json().get("detail", "")
    
    # Test 3: Valid token but wrong role should return 403
    # Token lacking any allowed workflow roles (attending/resident/scribe); exclude admin to test denial path
    wrong_role_token = generate_test_token(["patient"])  # Not allowed roles
    wrong_role_headers = {"Authorization": f"Bearer {wrong_role_token}"}
    response = client.post(f"/api/v1/workflows/{patient_id}/start", headers=wrong_role_headers)
    assert response.status_code == 403
    assert "Insufficient permissions" in response.json().get("detail", "")
    
    # Test 4: Valid token with correct role should succeed
    valid_token = generate_test_token(["attending"])  # Allowed role
    valid_headers = {"Authorization": f"Bearer {valid_token}"}
    response = client.post(f"/api/v1/workflows/{patient_id}/start", headers=valid_headers)
    # Should succeed (200) or at least not fail due to auth (not 401/403)
    assert response.status_code not in [401, 403]
    # May be 200 or 500 (due to workflow execution), but auth should pass
    
    # Test 5: Test canvas update endpoint auth
    canvas_update_data = {
        "content_md": "Test content",
        "version": 1,
        "content_json": {"test": "data"}
    }
    
    # Missing auth
    response = client.post(f"/api/v1/canvases/{patient_id}/1", json=canvas_update_data)
    assert response.status_code in [401, 403]  # Either is acceptable
    
    # Wrong role
    response = client.post(f"/api/v1/canvases/{patient_id}/1", json=canvas_update_data, headers=wrong_role_headers)
    assert response.status_code == 403
    
    # Valid role - should pass auth
    valid_token_resident = generate_test_token(["resident"])  # Another allowed role
    resident_headers = {"Authorization": f"Bearer {valid_token_resident}"}
    response = client.post(f"/api/v1/canvases/{patient_id}/1", json=canvas_update_data, headers=resident_headers)
    assert response.status_code not in [401, 403]  # Auth should pass
    
    # Test 6: Multiple roles where one is allowed
    mixed_roles_token = generate_test_token(["patient", "scribe", "admin"])  # scribe is allowed
    mixed_headers = {"Authorization": f"Bearer {mixed_roles_token}"}
    response = client.post(f"/api/v1/workflows/{patient_id}/start", headers=mixed_headers)
    assert response.status_code not in [401, 403]  # Should pass due to scribe role


def test_token_expiration():
    """Test that expired tokens are rejected."""
    from datetime import datetime, timedelta, timezone
    import jwt
    from app.auth.security import JWT_SECRET, JWT_ALGORITHM
    
    # Create an expired token
    expired_payload = {
        "roles": ["attending"],
    "exp": datetime.now(timezone.utc) - timedelta(hours=1),  # 1 hour ago
    "iat": datetime.now(timezone.utc) - timedelta(hours=2),
        "type": "access"
    }
    expired_token = jwt.encode(expired_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    expired_headers = {"Authorization": f"Bearer {expired_token}"}
    
    response = client.post("/api/v1/workflows/test_patient/start", headers=expired_headers)
    assert response.status_code == 401
    assert "expired" in response.json().get("detail", "").lower()


def test_no_roles_in_token():
    """Test that tokens without roles are rejected."""
    import jwt
    from datetime import datetime, timedelta, timezone
    from app.auth.security import JWT_SECRET, JWT_ALGORITHM
    
    # Create a token without roles
    payload_no_roles = {
    "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    "iat": datetime.now(timezone.utc),
        "user": "test_user"
        # No roles field
    }
    no_roles_token = jwt.encode(payload_no_roles, JWT_SECRET, algorithm=JWT_ALGORITHM)
    no_roles_headers = {"Authorization": f"Bearer {no_roles_token}"}
    
    response = client.post("/api/v1/workflows/test_patient/start", headers=no_roles_headers)
    assert response.status_code == 403
    assert "No roles found" in response.json().get("detail", "")


if __name__ == "__main__":
    test_jwt_auth_enforcement()
    test_token_expiration()
    test_no_roles_in_token()
    print("✓ JWT authentication tests passed")