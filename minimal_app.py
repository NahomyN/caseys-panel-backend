"""
Minimal FastAPI app for Casey's Panel Backend
"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Create app
app = FastAPI(title="Casey's Panel Backend", version="1.0.0")

# CORS configuration
FRONTEND_ORIGINS = os.getenv("FRONTEND_ORIGINS", "https://caseys-panel.aclera-ai.com,https://wonderful-field-03d5df610.1.azurestaticapps.net").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/healthz")
async def health_check():
    return JSONResponse(content={"ok": True, "message": "Backend is running"})

@app.get("/")
async def root():
    return JSONResponse(content={
        "service": "Casey's Panel Backend",
        "version": "1.0.0",
        "status": "running"
    })

@app.get("/api/v1/auth/google-client-id")
async def get_google_client_id():
    client_id = os.getenv("GOOGLE_CLIENT_ID", "153410214288-poq46sd9781qukuhsgc9313u8lh57ti1.apps.googleusercontent.com")
    return JSONResponse(content={"clientId": client_id})

@app.post("/api/v1/auth/google")
async def google_auth():
    # Simplified auth for testing
    return JSONResponse(content={
        "access_token": "test_token",
        "token_type": "bearer",
        "user": {
            "email": "test@example.com",
            "name": "Test User"
        }
    })

@app.get("/api/v1/workflows")
async def get_workflows():
    return JSONResponse(content={"workflows": []})

@app.post("/api/v1/workflows/start")
async def start_workflow():
    return JSONResponse(content={
        "id": "test-workflow-1",
        "status": "started",
        "message": "Test workflow started"
    })

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
