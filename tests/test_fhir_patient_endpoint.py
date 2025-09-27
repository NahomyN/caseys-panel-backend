"""Test FHIR Patient endpoint."""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.auth.security import generate_test_token


client = TestClient(app)


def test_fhir_patient_endpoint():
    """Test basic FHIR Patient endpoint functionality."""
    # Create token with required role
    token = generate_test_token(["attending"])
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test patient ID
    patient_id = "test_fhir_patient_123"
    
    # Call FHIR endpoint
    response = client.get(f"/api/v1/fhir/Patient/{patient_id}", headers=headers)
    assert response.status_code == 200
    
    # Check FHIR R4 Patient resource structure
    patient = response.json()
    
    # Required FHIR fields
    assert patient["resourceType"] == "Patient"
    assert patient["id"] == patient_id
    assert patient["active"] == True
    
    # Should have identifier
    assert "identifier" in patient
    assert len(patient["identifier"]) > 0
    assert patient["identifier"][0]["use"] == "usual"
    assert "value" in patient["identifier"][0]
    
    # Should have name
    assert "name" in patient
    assert len(patient["name"]) > 0
    assert patient["name"][0]["use"] == "official"
    assert patient["name"][0]["family"] == "Patient"
    assert "given" in patient["name"][0]
    
    # Should have meta
    assert "meta" in patient
    assert "versionId" in patient["meta"]
    assert "lastUpdated" in patient["meta"]
    
    print("✅ FHIR Patient endpoint returns valid FHIR R4 structure")


def test_fhir_patient_role_protection():
    """Test that FHIR endpoint requires correct roles."""
    patient_id = "test_fhir_patient_auth"
    
    # Test without auth header
    response = client.get(f"/api/v1/fhir/Patient/{patient_id}")
    assert response.status_code in [401, 403]
    
    # Test with wrong role
    wrong_role_token = generate_test_token(["patient"])  # Not allowed
    wrong_headers = {"Authorization": f"Bearer {wrong_role_token}"}
    response = client.get(f"/api/v1/fhir/Patient/{patient_id}", headers=wrong_headers)
    assert response.status_code == 403
    
    # Test with correct roles
    for role in ["attending", "resident", "scribe"]:
        correct_token = generate_test_token([role])
        correct_headers = {"Authorization": f"Bearer {correct_token}"}
        response = client.get(f"/api/v1/fhir/Patient/{patient_id}", headers=correct_headers)
        assert response.status_code == 200, f"Role {role} should have access"
    
    print("✅ FHIR Patient endpoint properly protected by role")


def test_fhir_patient_identifier_consistency():
    """Test that patient identifiers are consistent for same patient."""
    token = generate_test_token(["attending"])
    headers = {"Authorization": f"Bearer {token}"}
    
    patient_id = "consistent_test_patient"
    
    # Make two requests for same patient
    response1 = client.get(f"/api/v1/fhir/Patient/{patient_id}", headers=headers)
    response2 = client.get(f"/api/v1/fhir/Patient/{patient_id}", headers=headers)
    
    assert response1.status_code == 200
    assert response2.status_code == 200
    
    patient1 = response1.json()
    patient2 = response2.json()
    
    # Should have same identifier (deterministic hashing)
    assert patient1["identifier"][0]["value"] == patient2["identifier"][0]["value"]
    assert patient1["name"][0]["given"] == patient2["name"][0]["given"]
    
    print("✅ FHIR Patient identifiers are consistent")


def test_fhir_patient_different_patients():
    """Test that different patients get different identifiers."""
    token = generate_test_token(["resident"])
    headers = {"Authorization": f"Bearer {token}"}
    
    # Get two different patients
    response1 = client.get("/api/v1/fhir/Patient/patient_a", headers=headers)
    response2 = client.get("/api/v1/fhir/Patient/patient_b", headers=headers)
    
    assert response1.status_code == 200
    assert response2.status_code == 200
    
    patient1 = response1.json()
    patient2 = response2.json()
    
    # Should have different identifiers
    assert patient1["identifier"][0]["value"] != patient2["identifier"][0]["value"]
    assert patient1["name"][0]["given"] != patient2["name"][0]["given"]
    
    # But same structure
    assert patient1["resourceType"] == patient2["resourceType"] == "Patient"
    assert patient1["active"] == patient2["active"] == True
    
    print("✅ Different patients get different FHIR identifiers")


def test_fhir_patient_admin_access():
    """Test that admin role can access FHIR endpoint."""
    # Admin should have wildcard access
    admin_token = generate_test_token(["admin"])
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    
    response = client.get("/api/v1/fhir/Patient/admin_test_patient", headers=admin_headers)
    assert response.status_code == 200
    
    patient = response.json()
    assert patient["resourceType"] == "Patient"
    
    print("✅ Admin role can access FHIR endpoint")


def test_fhir_patient_schema_keys():
    """Test that FHIR Patient has expected schema keys."""
    token = generate_test_token(["scribe"])
    headers = {"Authorization": f"Bearer {token}"}
    
    response = client.get("/api/v1/fhir/Patient/schema_test", headers=headers)
    assert response.status_code == 200
    
    patient = response.json()
    
    # Check all expected top-level keys are present
    required_keys = ["resourceType", "id", "identifier", "active", "name", "meta"]
    for key in required_keys:
        assert key in patient, f"Missing required key: {key}"
    
    # Check identifier structure
    identifier = patient["identifier"][0]
    assert "use" in identifier
    assert "value" in identifier
    
    # Check name structure
    name = patient["name"][0]
    assert "use" in name
    assert "family" in name
    assert "given" in name
    
    # Check meta structure
    meta = patient["meta"]
    assert "versionId" in meta
    assert "lastUpdated" in meta
    
    print("✅ FHIR Patient has all expected schema keys")


if __name__ == "__main__":
    test_fhir_patient_endpoint()
    test_fhir_patient_role_protection()
    test_fhir_patient_identifier_consistency()
    test_fhir_patient_different_patients()
    test_fhir_patient_admin_access()
    test_fhir_patient_schema_keys()