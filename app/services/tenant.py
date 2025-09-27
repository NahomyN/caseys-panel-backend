"""Multi-tenant support utilities."""
from typing import Optional
from fastapi import Request, Header


def get_tenant_id(request: Request = None, x_tenant: Optional[str] = Header(None)) -> str:
    """Get tenant ID from request headers or default."""
    # Check X-Tenant header first
    if x_tenant:
        return x_tenant
    
    # Check query parameter as fallback
    if request and hasattr(request, 'query_params'):
        tenant_param = request.query_params.get('tenant')
        if tenant_param:
            return tenant_param
    
    # Default tenant
    return "default"