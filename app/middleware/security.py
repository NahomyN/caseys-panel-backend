import os
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response, RedirectResponse


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        app_env = os.getenv("APP_ENV", "development")

        # HTTPS enforcement in production
        if app_env == "production":
            # Check if request is HTTPS
            if request.url.scheme != "https":
                # Get the host from headers (Azure load balancer may terminate SSL)
                host = request.headers.get("host", request.url.hostname)
                https_url = f"https://{host}{request.url.path}"
                if request.url.query:
                    https_url += f"?{request.url.query}"
                return RedirectResponse(url=https_url, status_code=301)

        response = await call_next(request)

        # Core security headers for all environments
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=(), payment=()")

        # Production-specific headers
        if app_env == "production":
            # Strict HSTS for production with preload
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains; preload")
            # Very restrictive CSP for API-only backend
            response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        else:
            # Development: Less strict HSTS without preload
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")

        # Azure App Service specific headers
        if "azurewebsites.net" in request.headers.get("host", ""):
            response.headers.setdefault("X-Powered-By", "")  # Remove Azure default header

        return response




