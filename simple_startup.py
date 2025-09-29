#!/usr/bin/env python3
"""
Simple startup test for Azure App Service
"""
import sys
import os

def main():
    print(f"Python executable: {sys.executable}")
    print(f"Python version: {sys.version}")
    print(f"Working directory: {os.getcwd()}")
    print(f"Environment variables:")
    for key, value in os.environ.items():
        if any(k in key.upper() for k in ["APP", "PYTHON", "PORT", "WEBSITE"]):
            print(f"  {key}={value[:50]}...")
    
    # Test imports
    print("\nTesting imports...")
    try:
        import fastapi
        print("✓ FastAPI imported successfully")
    except ImportError as e:
        print(f"✗ FastAPI import failed: {e}")
    
    try:
        import uvicorn
        print("✓ Uvicorn imported successfully")
    except ImportError as e:
        print(f"✗ Uvicorn import failed: {e}")
    
    try:
        import gunicorn
        print("✓ Gunicorn imported successfully")
    except ImportError as e:
        print(f"✗ Gunicorn import failed: {e}")
    
    # Try to import app
    print("\nTrying to import the app...")
    try:
        from app.main import app
        print("✓ App imported successfully")
        
        # Start simple server
        port = int(os.environ.get("PORT", 8000))
        print(f"\nStarting simple server on port {port}...")
        
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
    except Exception as e:
        print(f"✗ Failed to start app: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
