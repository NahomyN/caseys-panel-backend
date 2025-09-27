"""Test admin role wildcard access."""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.auth.security import generate_test_token
from app.services.database import SessionLocal, engine
from app.services.models import Base


client = TestClient(app)


def test_admin_wildcard():
    """Test that admin role provides wildcard access to all endpoints."""
    # Ensure tables exist
    Base.metadata.create_all(bind=engine)
    
    # Create admin token
    admin_token = generate_test_token(roles=["admin"])
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    
    # Test 1: Admin should access workflow endpoints (normally requiring attending/resident/scribe)
    response = client.post("/api/v1/workflows/admin_patient/start", headers=admin_headers)
    assert response.status_code not in [401, 403], "Admin should have access to workflow endpoints"
    
    # Test 2: Admin should access canvas endpoints
    canvas_data = {
        "content_md": "Admin test content",
        "version": 1,
        "content_json": {"admin": "test"}
    }
    response = client.post("/api/v1/canvases/admin_patient/1", json=canvas_data, headers=admin_headers)
    assert response.status_code not in [401, 403], "Admin should have access to canvas endpoints"
    
    # Test 3: Admin should access admin-only endpoints
    response = client.get("/api/v1/admin/daily-stats/2024-01-01", headers=admin_headers)
    # Should not fail due to auth (may fail due to no data, but that's different)
    assert response.status_code not in [401, 403], "Admin should access admin-only endpoints"
    
    # Test 4: Admin should access safety rules endpoint
    response = client.get("/api/v1/admin/safety-rules", headers=admin_headers)
    assert response.status_code not in [401, 403], "Admin should access safety rules endpoint"
    
    print("✅ Admin role provides wildcard access to all endpoints")


def test_admin_with_other_roles():
    """Test that admin role works even when combined with other roles."""
    # Create token with admin + other roles
    multi_role_token = generate_test_token(roles=["patient", "admin", "viewer"])
    multi_headers = {"Authorization": f"Bearer {multi_role_token}"}
    
    # Should still have access to attending-only endpoints due to admin role
    response = client.post("/api/v1/workflows/multi_patient/start", headers=multi_headers)
    assert response.status_code not in [401, 403], "Admin should override other role restrictions"
    
    # Should access admin-only endpoints
    response = client.get("/api/v1/admin/safety-rules", headers=multi_headers)
    assert response.status_code not in [401, 403], "Admin in multi-role should access admin endpoints"
    
    print("✅ Admin role works when combined with other roles")


def test_admin_role_precedence():
    """Test that admin role takes precedence over role restrictions."""
    admin_token = generate_test_token(roles=["admin"])
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    
    # Test endpoints that normally require specific roles
    endpoints_to_test = [
        ("POST", "/api/v1/workflows/test_patient/start"),  # Requires attending/resident/scribe
        ("GET", "/api/v1/admin/daily-stats/2024-01-01"),   # Requires attending/admin
        ("GET", "/api/v1/admin/safety-rules"),             # Requires attending/admin
    ]
    
    for method, endpoint in endpoints_to_test:
        if method == "POST":
            if "workflows" in endpoint:
                response = client.post(endpoint, headers=admin_headers)
            else:
                response = client.post(endpoint, json={}, headers=admin_headers)
        else:
            response = client.get(endpoint, headers=admin_headers)
        
        assert response.status_code not in [401, 403], f"Admin should access {method} {endpoint}"
    
    print("✅ Admin role precedence working correctly")


def test_non_admin_role_restrictions():
    """Test that non-admin roles still have restrictions."""
    # Create token with non-admin role
    limited_token = generate_test_token(roles=["viewer"])
    limited_headers = {"Authorization": f"Bearer {limited_token}"}
    
    # Should be denied access to workflow endpoints
    response = client.post("/api/v1/workflows/test_patient/start", headers=limited_headers)
    assert response.status_code == 403, "Non-admin should be denied access to protected endpoints"
    
    # Should be denied access to admin endpoints
    response = client.get("/api/v1/admin/safety-rules", headers=limited_headers)
    assert response.status_code == 403, "Non-admin should be denied access to admin endpoints"
    
    print("✅ Non-admin role restrictions still enforced")


def test_admin_patient_scope_interaction():
    """Test how admin role interacts with patient scope."""
    # Create admin token with specific patient scope
    admin_with_patients = generate_test_token(
        roles=["admin"],
        patients=["p1"]  # Limited patient scope
    )
    admin_headers = {"Authorization": f"Bearer {admin_with_patients}"}
    
    # Admin role should still respect patient scope when it's present
    response = client.post("/api/v1/workflows/p1/start", headers=admin_headers)
    assert response.status_code != 403, "Admin should access allowed patient"
    
    response = client.post("/api/v1/workflows/p2/start", headers=admin_headers)
    assert response.status_code == 403, "Admin with patient scope should still respect patient limits"
    
    print("✅ Admin role respects patient scope when present")


if __name__ == "__main__":
    test_admin_wildcard()
    test_admin_with_other_roles()
    test_admin_role_precedence()
    test_non_admin_role_restrictions()
    test_admin_patient_scope_interaction()