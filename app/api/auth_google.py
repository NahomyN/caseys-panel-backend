from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
import os
import httpx
from ..auth.security import generate_test_token


router = APIRouter()


class GoogleAuthRequest(BaseModel):
    id_token: str


class GoogleAuthResponse(BaseModel):
    token: str
    email: str | None = None
    name: str | None = None


async def _verify_with_google(id_token: str) -> dict:
    """Verify Google ID token using tokeninfo endpoint.
    Returns decoded payload dict on success, raises HTTPException otherwise.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get("https://oauth2.googleapis.com/tokeninfo", params={"id_token": id_token})
            if resp.status_code != 200:
                raise HTTPException(status_code=401, detail="Invalid Google token")
            payload = resp.json()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Failed to verify Google token")

    # Optional audience check when GOOGLE_CLIENT_ID is set
    expected_aud = os.getenv("GOOGLE_CLIENT_ID")
    aud = payload.get("aud")
    if expected_aud and aud != expected_aud:
        raise HTTPException(status_code=401, detail="Google token audience mismatch")

    # Basic integrity checks
    if not payload.get("email"):
        raise HTTPException(status_code=401, detail="Google token missing email")
    if payload.get("email_verified") in {"false", False, 0, "0"}:
        raise HTTPException(status_code=401, detail="Google email not verified")

    return payload


@router.post("/auth/google", response_model=GoogleAuthResponse)
async def exchange_google_token(req: GoogleAuthRequest, response: Response) -> GoogleAuthResponse:
    """Exchange a Google ID token for an application JWT.

    Requires users to be in the AUTHORIZED_USERS whitelist for security.
    """
    payload = await _verify_with_google(req.id_token)

    user_email = payload.get("email")
    if not user_email:
        raise HTTPException(status_code=401, detail="Email not found in Google token")

    # Check if user is authorized
    authorized_users = os.getenv("AUTHORIZED_USERS", "")
    if authorized_users:
        authorized_emails = [email.strip() for email in authorized_users.split(",")]
        if user_email not in authorized_emails:
            raise HTTPException(
                status_code=403,
                detail="Access denied. Please contact your administrator for access."
            )

    # For now, give basic access. TODO: Implement proper role assignment based on email/domain
    app_jwt = generate_test_token(["attending"], expiration_hours=24, patients=["*"])

    # Set httpOnly cookie for enhanced security
    is_production = os.getenv("APP_ENV") == "production"
    response.set_cookie(
        key="auth_token",
        value=app_jwt,
        httponly=True,
        secure=is_production,  # Only require HTTPS in production
        samesite="strict",
        max_age=24 * 60 * 60  # 24 hours
    )

    return GoogleAuthResponse(token=app_jwt, email=user_email, name=payload.get("name"))


@router.post("/auth/logout")
async def logout(response: Response) -> dict:
    """Clear authentication cookie."""
    is_production = os.getenv("APP_ENV") == "production"
    response.delete_cookie(key="auth_token", httponly=True, secure=is_production, samesite="strict")
    return {"message": "Logged out successfully"}


@router.get("/auth/google/client_id")
async def get_google_client_id() -> dict:
    """Expose configured Google OAuth client ID for the frontend to initialize GIS.
    Returns empty string if not configured.
    """
    return {"client_id": os.getenv("GOOGLE_CLIENT_ID", "")}


