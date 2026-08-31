from typing import Set

from fastapi import HTTPException, status

from backend.app.models.user import User, UserRole


def check_role(user: User, allowed_roles: Set[UserRole]) -> None:
    """Validate that the authenticated user possesses one of the allowed roles.
    
    Raises HTTP 403 Forbidden if the role is insufficient.
    """
    if user.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to access this resource",
        )


def check_tenant(user: User, target_tenant_id: str) -> None:
    """Validate that the target tenant scope matches the authenticated user's tenant_id.
    
    Raises HTTP 403 Forbidden on tenant mismatch.
    
    Note: This is a route-level authorization helper. Future document and retrieval
    subsystems will also enforce tenant scoping directly at the database query boundary
    (WHERE tenant_id = :tenant_id) using the authoritative user.tenant_id.
    """
    if user.tenant_id != target_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-tenant access forbidden",
        )
