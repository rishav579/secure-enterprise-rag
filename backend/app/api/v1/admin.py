from fastapi import APIRouter, Depends, status

from backend.app.api.deps import require_admin, verify_tenant_access
from backend.app.models.user import User

router = APIRouter(prefix="/admin", tags=["Administration"])


@router.get(
    "/dashboard",
    status_code=status.HTTP_200_OK,
    summary="Admin dashboard endpoint (restricted to administrators)",
)
async def admin_dashboard(
    current_admin: User = Depends(require_admin),
):
    """Retrieve administrative dashboard status.
    
    Strictly protected by require_admin dependency (returns 403 for authenticated employees).
    """
    return {
        "status": "authorized",
        "message": "Welcome to the administrative portal",
        "role": current_admin.role,
        "admin_id": str(current_admin.id),
        "tenant_id": current_admin.tenant_id,
    }


@router.get(
    "/tenants/{tenant_id}/data",
    status_code=status.HTTP_200_OK,
    summary="Access tenant administrative resources with tenant scope verification",
)
async def admin_tenant_data(
    tenant_id: str,
    current_admin: User = Depends(require_admin),
):
    """Access tenant-specific administrative resources.
    
    Verifies that the target tenant matches the authenticated user's authoritative tenant_id.
    """
    verify_tenant_access(current_admin, tenant_id)
    return {
        "status": "authorized",
        "tenant_id": current_admin.tenant_id,
        "data": f"Sensitive data for tenant {tenant_id}",
    }
