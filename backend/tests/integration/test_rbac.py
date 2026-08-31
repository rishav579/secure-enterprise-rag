import uuid
from datetime import timedelta
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.security import create_access_token, hash_password
from backend.app.models.user import User, UserRole


async def create_test_user(
    db: AsyncSession,
    email: str,
    role: UserRole = UserRole.EMPLOYEE,
    tenant_id: str = "default",
    is_active: bool = True,
) -> tuple[User, str]:
    """Helper to create a user and signed token directly in the database session."""
    user = User(
        email=email,
        hashed_password=hash_password("Password123!"),
        role=role,
        tenant_id=tenant_id,
        is_active=is_active,
    )
    db.add(user)
    await db.flush()
    token = create_access_token(subject=user.id)
    return user, token


# ============================================================================
# Role-Based Authorization Tests
# ============================================================================

@pytest.mark.asyncio
async def test_admin_allowed_on_admin_endpoint(client: AsyncClient, test_db_session: AsyncSession):
    """Verify administrator user is granted access (HTTP 200) to admin dashboard."""
    _, admin_token = await create_test_user(
        test_db_session,
        email="verified.admin@enterprise.com",
        role=UserRole.ADMIN,
    )

    response = await client.get(
        "/api/v1/admin/dashboard",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "authorized"
    assert data["role"] == "admin"


@pytest.mark.asyncio
async def test_employee_denied_on_admin_endpoint(client: AsyncClient, test_db_session: AsyncSession):
    """Verify authenticated employee receives HTTP 403 Forbidden on admin dashboard."""
    _, employee_token = await create_test_user(
        test_db_session,
        email="regular.employee@enterprise.com",
        role=UserRole.EMPLOYEE,
    )

    response = await client.get(
        "/api/v1/admin/dashboard",
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert response.status_code == 403
    data = response.json()
    assert "Insufficient permissions" in data["detail"]
    # 403 authorization failures must NOT include WWW-Authenticate header
    assert "www-authenticate" not in response.headers


# ============================================================================
# 401 Authentication vs 403 Authorization Boundary Tests
# ============================================================================

@pytest.mark.asyncio
async def test_unauthenticated_request_returns_401_with_www_authenticate(client: AsyncClient):
    """Verify missing credentials return HTTP 401 with WWW-Authenticate header."""
    response = await client.get("/api/v1/admin/dashboard")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.asyncio
async def test_invalid_jwt_returns_401_on_protected_endpoint(client: AsyncClient):
    """Verify invalid token signature or format returns HTTP 401."""
    response = await client.get(
        "/api/v1/admin/dashboard",
        headers={"Authorization": "Bearer invalid.signature.token"},
    )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.asyncio
async def test_expired_jwt_returns_401_on_protected_endpoint(client: AsyncClient, test_db_session: AsyncSession):
    """Verify expired token returns HTTP 401 even for an admin user."""
    admin_user, _ = await create_test_user(
        test_db_session,
        email="expired.admin@enterprise.com",
        role=UserRole.ADMIN,
    )
    expired_token = create_access_token(
        subject=admin_user.id,
        expires_delta=timedelta(seconds=-30),
    )

    response = await client.get(
        "/api/v1/admin/dashboard",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert "expired" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_inactive_admin_returns_401(client: AsyncClient, test_db_session: AsyncSession):
    """Verify inactive admin is rejected at the authentication boundary (HTTP 401)."""
    _, inactive_admin_token = await create_test_user(
        test_db_session,
        email="inactive.admin@enterprise.com",
        role=UserRole.ADMIN,
        is_active=False,
    )

    response = await client.get(
        "/api/v1/admin/dashboard",
        headers={"Authorization": f"Bearer {inactive_admin_token}"},
    )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


# ============================================================================
# Tenant Boundary Tests
# ============================================================================

@pytest.mark.asyncio
async def test_tenant_access_match_allowed(client: AsyncClient, test_db_session: AsyncSession):
    """Verify admin accessing data within their own tenant scope succeeds (HTTP 200)."""
    _, admin_token = await create_test_user(
        test_db_session,
        email="tenant_alpha.admin@enterprise.com",
        role=UserRole.ADMIN,
        tenant_id="tenant_alpha",
    )

    response = await client.get(
        "/api/v1/admin/tenants/tenant_alpha/data",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "authorized"
    assert data["tenant_id"] == "tenant_alpha"


@pytest.mark.asyncio
async def test_tenant_access_mismatch_denied(client: AsyncClient, test_db_session: AsyncSession):
    """Verify user in tenant_alpha attempting to access tenant_beta is rejected with HTTP 403."""
    _, admin_token = await create_test_user(
        test_db_session,
        email="tenant_alpha.admin@enterprise.com",
        role=UserRole.ADMIN,
        tenant_id="tenant_alpha",
    )

    response = await client.get(
        "/api/v1/admin/tenants/tenant_beta/data",  # Mismatched tenant
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 403
    assert "Cross-tenant access forbidden" in response.json()["detail"]


# ============================================================================
# Privilege Escalation & Parameter Tampering Immunity Tests
# ============================================================================

@pytest.mark.asyncio
async def test_employee_cannot_escalate_via_query_params_or_headers(client: AsyncClient, test_db_session: AsyncSession):
    """Verify employee cannot escalate privileges by passing role or tenant parameters."""
    _, employee_token = await create_test_user(
        test_db_session,
        email="sneaky.employee@enterprise.com",
        role=UserRole.EMPLOYEE,
        tenant_id="tenant_alpha",
    )

    # Attempt escalation via query parameters and headers
    response = await client.get(
        "/api/v1/admin/dashboard?role=admin&tenant_id=tenant_beta",
        headers={
            "Authorization": f"Bearer {employee_token}",
            "X-Role": "admin",
            "X-Tenant-ID": "tenant_beta",
        },
    )
    # Server-side authoritative state must strictly deny access with 403
    assert response.status_code == 403
    assert "Insufficient permissions" in response.json()["detail"]
