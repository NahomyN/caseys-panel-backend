#!/usr/bin/env python3
"""
Startup script for Azure App Service
Ensures proper Python environment and starts the application
"""
import sys
import os
import subprocess

def main():
    # Ensure we're using the right Python environment
    print(f"Python executable: {sys.executable}")
    print(f"Python version: {sys.version}")
    print(f"Working directory: {os.getcwd()}")

    # Install dependencies if needed
    try:
        import uvicorn
        import fastapi
        import gunicorn
        print("All dependencies are available")
    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("Installing dependencies...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

    # Start the application
    os.environ.setdefault("PORT", "8000")
    port = int(os.environ.get("PORT", 8000))

    cmd = [
        sys.executable, "-m", "gunicorn",
        "app.main:app",
        "--workers", "4",
        "--worker-class", "uvicorn.workers.UvicornWorker",
        "--bind", f"0.0.0.0:{port}",
        "--timeout", "120",
        "--access-logfile", "-",
        "--error-logfile", "-"
    ]

    print(f"Starting application with command: {' '.join(cmd)}")
    os.execv(sys.executable, cmd)

if __name__ == "__main__":
    main()