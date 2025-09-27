"""Main FastAPI application for Casey's Panel Backend"""

import os
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api import workflows, auth, canvases, workflow
from .services.database import init_db
from .services.websocket import ws_manager
from .middleware.phi import PHIMiddleware

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Get environment
APP_ENV = os.getenv("APP_ENV", "development")
FRONTEND_ORIGINS = os.getenv("FRONTEND_ORIGINS", "http://localhost:3000").split(",")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    logger.info(f"Starting Casey's Panel Backend in {APP_ENV} mode")
    
    # Initialize database - temporarily disabled for startup issues
    # await init_db()

    # Initialize WebSocket manager - temporarily disabled for startup issues
    # await ws_manager.initialize()
    
    yield
    
    # Cleanup - temporarily disabled for startup issues
    # await ws_manager.cleanup()
    logger.info("Shutting down Casey's Panel Backend")

# Create FastAPI app
app = FastAPI(
    title="Casey's Panel Backend",
    description="HIPAA-compliant medical workflow management system with AI agents",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if APP_ENV != "production" else None,
    redoc_url="/redoc" if APP_ENV != "production" else None
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Process-Time"]
)

# Add PHI protection middleware
app.add_middleware(PHIMiddleware)

# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    
    if APP_ENV == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # CSP allowing Google OAuth
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' https://accounts.google.com https://apis.google.com; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https://ssl.gstatic.com https://accounts.google.com; "
            "connect-src 'self' https://accounts.google.com https://oauth2.googleapis.com https://www.googleapis.com; "
            "frame-src https://accounts.google.com; "
            "object-src 'none'; "
            "base-uri 'none'"
        )
    
    return response

# Health check endpoint
@app.get("/healthz")
async def health_check():
    """Health check endpoint for monitoring"""
    return JSONResponse(
        content={
            "ok": True,
            "message": "Casey's Panel Backend is running",
            "environment": APP_ENV,
            "version": "1.0.0"
        }
    )

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with service information"""
    return JSONResponse(
        content={
            "service": "Casey's Panel Backend",
            "version": "1.0.0",
            "status": "running",
            "description": "Medical workflow management system - " + APP_ENV.title(),
            "environment": APP_ENV,
            "endpoints": {
                "health": "/healthz",
                "docs": "/docs" if APP_ENV != "production" else None,
                "workflows": "/api/v1/workflows",
                "canvases": "/api/v1/canvases",
                "auth": "/api/v1/auth",
                "websocket": "/api/v1/ws"
            }
        }
    )

# Include API routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(workflows.router, prefix="/api/v1/workflows", tags=["Workflows"])
app.include_router(canvases.router, prefix="/api/v1/canvases", tags=["Canvases"])
app.include_router(workflow.router, prefix="/api/v1", tags=["Hospitalist Workflow"])

# WebSocket endpoint
app.websocket("/api/v1/ws")(ws_manager.websocket_endpoint)

# Error handlers
@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return JSONResponse(
        status_code=404,
        content={"detail": "Resource not found"}
    )

@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    logger.error(f"Internal server error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=APP_ENV == "development"
    )