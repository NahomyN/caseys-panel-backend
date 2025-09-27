import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.database import SessionLocal, engine
from app.services.models import Base, Canvas
from app.auth.security import generate_test_token
import json


client = TestClient(app)


def test_canvas_version_conflict():
    """Test that canvas version conflicts are properly detected and handled."""
    # Ensure tables exist
    Base.metadata.create_all(bind=engine)
    
    # Create auth headers
    token = generate_test_token(["attending"])
    headers = {"Authorization": f"Bearer {token}"}
    
    patient_id = "test_patient_version"
    agent_no = 1
    
    # Clean up any existing canvas
    with SessionLocal() as session:
        existing = session.query(Canvas).filter(
            Canvas.patient_id == patient_id,
            Canvas.agent_no == agent_no
        ).first()
        if existing:
            session.delete(existing)
            session.commit()
    
    # Create initial canvas
    initial_request = {
        "content_md": "Initial content",
        "version": 1,  # For new canvas, version 1 is expected
        "content_json": {"note": "initial"}
    }
    
    # First create should succeed (there's no existing canvas)
    response = client.post(
        f"/api/v1/canvases/{patient_id}/{agent_no}",
        json=initial_request,
        headers=headers
    )
    assert response.status_code == 200
    created_canvas = response.json()
    assert created_canvas["version"] == 1
    assert created_canvas["content_md"] == "Initial content"
    
    # Update with correct version should succeed
    update_request = {
        "content_md": "Updated content",
        "version": 1,  # Current version
        "content_json": {"note": "updated"}
    }
    
    response = client.post(
        f"/api/v1/canvases/{patient_id}/{agent_no}",
        json=update_request,
        headers=headers
    )
    assert response.status_code == 200
    updated_canvas = response.json()
    assert updated_canvas["version"] == 2  # Should increment
    assert updated_canvas["content_md"] == "Updated content"
    
    # Update with stale version should fail with 409
    stale_request = {
        "content_md": "Stale update attempt",
        "version": 1,  # Stale version (current is 2)
        "content_json": {"note": "stale"}
    }
    
    response = client.post(
        f"/api/v1/canvases/{patient_id}/{agent_no}",
        json=stale_request,
        headers=headers
    )
    assert response.status_code == 409
    
    error_detail = response.json()["detail"]
    assert error_detail["error"] == "Version conflict - client version is stale"
    assert error_detail["client_version"] == 1
    assert error_detail["current_version"] == 2
    assert error_detail["current_content_md"] == "Updated content"
    
    # Update with correct current version should work
    correct_request = {
        "content_md": "Final content",
        "version": 2,  # Current version
        "content_json": {"note": "final"}
    }
    
    response = client.post(
        f"/api/v1/canvases/{patient_id}/{agent_no}",
        json=correct_request,
        headers=headers
    )
    assert response.status_code == 200
    final_canvas = response.json()
    assert final_canvas["version"] == 3  # Should increment again
    assert final_canvas["content_md"] == "Final content"


def test_canvas_version_increment_on_success():
    """Test that canvas version increments on successful updates."""
    Base.metadata.create_all(bind=engine)
    
    # Create auth headers
    token = generate_test_token(["resident"])
    headers = {"Authorization": f"Bearer {token}"}
    
    patient_id = "test_patient_increment"
    agent_no = 2
    
    # Clean up
    with SessionLocal() as session:
        existing = session.query(Canvas).filter(
            Canvas.patient_id == patient_id,
            Canvas.agent_no == agent_no
        ).first()
        if existing:
            session.delete(existing)
            session.commit()
    
    # Create canvas with version 1
    request1 = {
        "content_md": "Version 1",
        "version": 1,
        "content_json": None
    }
    
    response1 = client.post(f"/api/v1/canvases/{patient_id}/{agent_no}", json=request1, headers=headers)
    assert response1.status_code == 200
    assert response1.json()["version"] == 1
    
    # Multiple successful updates should increment version each time
    for i in range(2, 6):  # versions 2-5
        request = {
            "content_md": f"Version {i}",
            "version": i - 1,  # Previous version
            "content_json": {"iteration": i}
        }
        
        response = client.post(f"/api/v1/canvases/{patient_id}/{agent_no}", json=request, headers=headers)
        assert response.status_code == 200
        assert response.json()["version"] == i


if __name__ == "__main__":
    test_canvas_version_conflict()
    test_canvas_version_increment_on_success()
    print("✓ Canvas version conflict tests passed")