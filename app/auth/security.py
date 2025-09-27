import os
import jwt
from typing import List, Optional
from fastapi import HTTPException, Depends, status, Request, Cookie
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime, timedelta, timezone
from ..services.rate_limiting import check_rate_limit


# JWT Configuration
JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    if os.getenv("APP_ENV") == "production":
        raise ValueError("JWT_SECRET environment variable is required for production")
    JWT_SECRET = "dev-secret-INSECURE-TESTING-ONLY"  # Clear it's for testing
JWT_ALGORITHM = "HS256"

security = HTTPBearer()


def generate_test_token(roles: List[str], expiration_hours: int = 24, patients: Optional[List[str]] = None) -> str:
    """Generate JWT token for testing purposes."""
    payload = {
        "roles": roles,
        "exp": datetime.now(timezone.utc) + timedelta(hours=expiration_hours),
        "iat": datetime.now(timezone.utc),
        "type": "access"
    }
    
    # Add patients claim if provided
    if patients is not None:
        payload["patients"] = patients
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_jwt(token: str) -> dict:
    """Verify JWT token and return payload."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )


def require_roles(allowed_roles: List[str]):
    """FastAPI dependency that requires specific roles with rate limiting."""
    def auth_dependency(
        request: Request,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
        auth_token: Optional[str] = Cookie(None)
    ):
        token = None

        # Try to get token from Authorization header first, then from cookie
        if credentials:
            token = credentials.credentials
        elif auth_token:
            token = auth_token

        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization required"
            )

        # Check rate limit first (using token for subject)
        check_rate_limit(request, token)

        # Verify token
        payload = verify_jwt(token)
        
        # Check roles
        user_roles = payload.get("roles", [])
        if not user_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No roles found in token"
            )
        
        # Check if user has any of the allowed roles (including "admin" wildcard)
        if not any(role in allowed_roles or role == "admin" for role in user_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required roles: {allowed_roles}"
            )
        
        return payload
    
    return auth_dependency


def require_patient_access(patient_id: str):
    """FastAPI dependency that requires access to a specific patient."""
    def patient_auth_dependency(
        request: Request,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
        auth_token: Optional[str] = Cookie(None)
    ):
        token = None

        # Try to get token from Authorization header first, then from cookie
        if credentials:
            token = credentials.credentials
        elif auth_token:
            token = auth_token

        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization required"
            )

        # Check rate limit
        check_rate_limit(request, token)

        # Verify token
        payload = verify_jwt(token)
        
        # Check patient access
        patients = payload.get("patients", None)
        
        # If no patients claim, allow for backward compatibility (with warning log)
        if patients is None:
            import logging
            logging.warning(f"Token missing patients claim - allowing access for backward compatibility")
            return payload
        
        # If wildcard access, allow
        if "*" in patients:
            return payload
        
        # If patient_id in allowed list, allow
        if patient_id in patients:
            return payload
        
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied for patient {patient_id}"
        )
    
    return patient_auth_dependency


def enforce_patient_scope(payload: dict, patient_id: str):
    """Programmatic patient scope enforcement using an already-verified JWT payload.
    Backward compatible: if no patients claim -> allow; empty list -> deny all; wildcard '*' -> allow all.
    Raises HTTPException 403 on denial.
    """
    patients = payload.get("patients", None)
    if patients is None:
        return  # backward compatibility
    # Explicit empty list denies all
    if len(patients) == 0:
        raise HTTPException(status_code=403, detail=f"Access denied for patient {patient_id}")
    if "*" in patients:
        return
    if patient_id in patients:
        return
    raise HTTPException(status_code=403, detail=f"Access denied for patient {patient_id}")