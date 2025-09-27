"""Authentication endpoints for Casey's Panel"""

import os
import jwt
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Response, Cookie, Depends
from pydantic import BaseModel
from google.oauth2 import id_token
from google.auth.transport import requests

logger = logging.getLogger(__name__)

router = APIRouter()

# Configuration
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "153410214288-poq46sd9781qukuhsgc9313u8lh57ti1.apps.googleusercontent.com")
AUTHORIZED_USERS = os.getenv("AUTHORIZED_USERS", "yirnah@gmail.com,nahom.nigussie@aclera-ai.com").split(",")

class GoogleAuthRequest(BaseModel):
    id_token: str
    flow_type: Optional[str] = "login"

class AuthResponse(BaseModel):
    token: str
    email: str
    name: Optional[str]
    is_new_user: bool = False

def create_jwt_token(email: str, name: Optional[str] = None) -> str:
    """Create JWT token for authenticated user"""
    payload = {
        "email": email,
        "name": name,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
        "iat": datetime.utcnow()
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_jwt_token(token: str) -> Optional[dict]:
    """Verify and decode JWT token"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

@router.post("/google", response_model=AuthResponse)
async def google_auth(request: GoogleAuthRequest, response: Response):
    """Authenticate with Google OAuth2"""
    try:
        # Verify the Google ID token
        idinfo = id_token.verify_oauth2_token(
            request.id_token, 
            requests.Request(), 
            GOOGLE_CLIENT_ID
        )
        
        email = idinfo.get("email")
        name = idinfo.get("name")
        
        # Check if user is authorized
        if email not in AUTHORIZED_USERS and AUTHORIZED_USERS[0] != "*":
            raise HTTPException(
                status_code=403, 
                detail="Access denied. Please contact administrator for access."
            )
        
        # Create JWT token
        token = create_jwt_token(email, name)
        
        # Set HTTP-only cookie
        response.set_cookie(
            key="auth_token",
            value=token,
            httponly=True,
            secure=os.getenv("APP_ENV") == "production",
            samesite="lax",
            max_age=JWT_EXPIRATION_HOURS * 3600
        )
        
        return AuthResponse(
            token=token,
            email=email,
            name=name,
            is_new_user=False
        )
        
    except ValueError as e:
        logger.error(f"Invalid Google token: {e}")
        raise HTTPException(status_code=401, detail="Invalid Google token")
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        raise HTTPException(status_code=500, detail="Authentication failed")

@router.post("/logout")
async def logout(response: Response):
    """Logout and clear auth cookie"""
    response.delete_cookie("auth_token")
    return {"message": "Logged out successfully"}

@router.get("/me")
async def get_current_user(auth_token: Optional[str] = Cookie(None)):
    """Get current user information from token"""
    if not auth_token:
        return {"authenticated": False}
    
    user_info = verify_jwt_token(auth_token)
    if not user_info:
        return {"authenticated": False}
    
    return {
        "authenticated": True,
        "email": user_info.get("email"),
        "name": user_info.get("name")
    }

@router.get("/google/client_id")
async def get_google_client_id():
    """Get Google OAuth client ID for frontend"""
    return {"client_id": GOOGLE_CLIENT_ID}
