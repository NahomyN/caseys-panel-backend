"""Test per-patient authorization enforcement."""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.auth.security import generate_test_token
from app.services.database import SessionLocal, engine
from app.services.models import Base


client = TestClient(app)


def test_patient_scope_enforced():
    """Test that tokens with patient scope are enforced."""
    # Ensure tables exist
    Base.metadata.create_all(bind=engine)
    
    # Create token with access to specific patients
    restricted_token = generate_test_token(
        roles=["attending"],
        patients=["p1", "p2"]  # Only has access to p1 and p2
    )
    restricted_headers = {"Authorization": f"Bearer {restricted_token}"}
    
    # Test 1: Should allow access to p1 (in allowed list)
    response = client.post("/api/v1/workflows/p1/start", headers=restricted_headers)
    assert response.status_code not in [403], "Should allow access to p1"
    
    # Test 2: Should allow access to p2 (in allowed list)
    response = client.post("/api/v1/workflows/p2/start", headers=restricted_headers)
    assert response.status_code not in [403], "Should allow access to p2"
    
    # Test 3: Should deny access to p3 (not in allowed list)
    response = client.post("/api/v1/workflows/p3/start", headers=restricted_headers)
    assert response.status_code == 403, "Should deny access to p3"
    assert "Access denied for patient p3" in response.json().get("detail", "")
    
    # Test 4: Canvas update should also be restricted
    canvas_data = {
        "content_md": "Test content",
        "version": 1,
        "content_json": {"test": "data"}
    }
    
    # Should allow p1
    response = client.post("/api/v1/canvases/p1/1", json=canvas_data, headers=restricted_headers)
    assert response.status_code != 403, "Should allow canvas access to p1"
    
    # Should deny p3
    response = client.post("/api/v1/canvases/p3/1", json=canvas_data, headers=restricted_headers)
    assert response.status_code == 403, "Should deny canvas access to p3"
    
    # Test 5: Final note access should be restricted
    response = client.get("/api/v1/final-note/p1", headers=restricted_headers)
    assert response.status_code != 403, "Should allow final note access to p1"
    
    response = client.get("/api/v1/final-note/p3", headers=restricted_headers)
    assert response.status_code == 403, "Should deny final note access to p3"
    
    print("✅ Patient scope enforcement working correctly")


def test_wildcard_patient_access():
    """Test that wildcard patient access works."""
    # Create token with wildcard access
    wildcard_token = generate_test_token(
        roles=["attending"],
        patients=["*"]  # Wildcard access
    )
    wildcard_headers = {"Authorization": f"Bearer {wildcard_token}"}
    
    # Should allow access to any patient
    patients_to_test = ["p1", "p2", "p3", "any_patient_id"]
    
    for patient_id in patients_to_test:
        response = client.post(f"/api/v1/workflows/{patient_id}/start", headers=wildcard_headers)
        assert response.status_code != 403, f"Wildcard should allow access to {patient_id}"
    
    print("✅ Wildcard patient access working correctly")


def test_backward_compatibility_no_patients_claim():
    """Test backward compatibility when token has no patients claim."""
    # Create token without patients claim (old format)
    old_format_token = generate_test_token(
        roles=["attending"]
        # No patients claim
    )
    old_headers = {"Authorization": f"Bearer {old_format_token}"}
    
    # Should allow access (with warning logged) for backward compatibility
    response = client.post("/api/v1/workflows/test_patient/start", headers=old_headers)
    assert response.status_code != 403, "Should allow access for backward compatibility"
    
    print("✅ Backward compatibility working for tokens without patients claim")


def test_empty_patients_list():
    """Test that empty patients list denies access."""
    # Create token with empty patients list
    no_access_token = generate_test_token(
        roles=["attending"],
        patients=[]  # Empty list - no access
    )
    no_access_headers = {"Authorization": f"Bearer {no_access_token}"}
    
    # Should deny access to any patient
    response = client.post("/api/v1/workflows/test_patient/start", headers=no_access_headers)
    assert response.status_code == 403, "Should deny access with empty patients list"
    
    print("✅ Empty patients list correctly denies access")


def test_patient_auth_with_role_check():
    """Test that both role and patient checks are applied."""
    # Create token with patient access but wrong role
    wrong_role_token = generate_test_token(
        roles=["patient"],  # Wrong role
        patients=["p1"]     # Has patient access
    )
    wrong_role_headers = {"Authorization": f"Bearer {wrong_role_token}"}
    
    # Should be denied due to role check (before patient check)
    response = client.post("/api/v1/workflows/p1/start", headers=wrong_role_headers)
    assert response.status_code == 403
    assert "Insufficient permissions" in response.json().get("detail", "")
    
    print("✅ Both role and patient authorization checks applied correctly")


if __name__ == "__main__":
    test_patient_scope_enforced()
    test_wildcard_patient_access()
    test_backward_compatibility_no_patients_claim()
    test_empty_patients_list()
    test_patient_auth_with_role_check()