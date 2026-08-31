import uuid
from datetime import timedelta
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.security import create_access_token, hash_password
from backend.app.models.user import User, UserRole


# ============================================================================
# Registration Tests
# ============================================================================

@pytest.mark.asyncio
async def test_successful_registration(client: AsyncClient):
    """Verify new user registration with default employee privileges."""
    payload = {
        "email": "New.Employee@Enterprise.Com ",  # Includes mixed case and trailing space
        "password": "StrongPassword2026#",
    }
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert data["email"] == "new.employee@enterprise.com"  # Normalized
    assert data["role"] == "employee"  # Safe default role
    assert data["tenant_id"] == "default"
    assert data["is_active"] is True
    assert "id" in data
    assert "created_at" in data
    assert "hashed_password" not in data
    assert "password" not in data


@pytest.mark.asyncio
async def test_registration_duplicate_email(client: AsyncClient):
    """Verify duplicate email registration is rejected with 409 Conflict."""
    payload = {
        "email": "duplicate@enterprise.com",
        "password": "StrongPassword2026#",
    }
    res1 = await client.post("/api/v1/auth/register", json=payload)
    assert res1.status_code == 201

    res2 = await client.post("/api/v1/auth/register", json=payload)
    assert res2.status_code == 409
    assert "already exists" in res2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_registration_invalid_input(client: AsyncClient):
    """Verify validation rejects malformed emails and invalid passwords."""
    # Invalid email format
    res = await client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "ValidPassword123!"},
    )
    assert res.status_code == 422

    # Password too short (<8 characters)
    res = await client.post(
        "/api/v1/auth/register",
        json={"email": "valid@enterprise.com", "password": "short"},
    )
    assert res.status_code == 422

    # Password too long (>72 bytes)
    res = await client.post(
        "/api/v1/auth/register",
        json={"email": "valid@enterprise.com", "password": "A" * 75},
    )
    assert res.status_code == 422

    # Blank password
    res = await client.post(
        "/api/v1/auth/register",
        json={"email": "valid@enterprise.com", "password": "   "},
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_registration_client_cannot_escalate_role(client: AsyncClient):
    """Verify client cannot inject role, tenant_id, or is_active during registration."""
    payload = {
        "email": "hacker@enterprise.com",
        "password": "Password123!",
        "role": "admin",  # Forbidden field
        "tenant_id": "malicious_tenant",
        "is_active": True,
    }
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422


# ============================================================================
# Login & Anti-Enumeration Tests
# ============================================================================

@pytest.mark.asyncio
async def test_successful_login(client: AsyncClient):
    """Verify login with valid credentials issues a JWT Bearer token."""
    # 1. Register user
    reg_payload = {"email": "login.user@enterprise.com", "password": "Password2026!"}
    await client.post("/api/v1/auth/register", json=reg_payload)

    # 2. Login
    login_payload = {"email": "LOGIN.USER@enterprise.com", "password": "Password2026!"}
    response = await client.post("/api/v1/auth/login", json=login_payload)
    assert response.status_code == 200
    data = response.json()

    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert len(data["access_token"]) > 20


@pytest.mark.asyncio
async def test_login_uniform_anti_enumeration(client: AsyncClient, test_db_session: AsyncSession):
    """Verify that unknown email, wrong password, and inactive user return identical 401 responses."""
    # Register active user
    await client.post(
        "/api/v1/auth/register",
        json={"email": "active.user@enterprise.com", "password": "Password123!"},
    )

    # Create inactive user directly in database
    inactive_user = User(
        email="inactive.user@enterprise.com",
        hashed_password=hash_password("Password123!"),
        role=UserRole.EMPLOYEE,
        is_active=False,
    )
    test_db_session.add(inactive_user)
    await test_db_session.flush()

    # 1. Unknown email
    res_unknown = await client.post(
        "/api/v1/auth/login",
        json={"email": "does.not.exist@enterprise.com", "password": "Password123!"},
    )
    # 2. Wrong password
    res_wrong_pw = await client.post(
        "/api/v1/auth/login",
        json={"email": "active.user@enterprise.com", "password": "WrongPassword!"},
    )
    # 3. Inactive account with correct password
    res_inactive = await client.post(
        "/api/v1/auth/login",
        json={"email": "inactive.user@enterprise.com", "password": "Password123!"},
    )

    # All three cases must return identical HTTP 401 with exact same message and header
    for res in [res_unknown, res_wrong_pw, res_inactive]:
        assert res.status_code == 401
        assert res.json()["detail"] == "Invalid email or password"
        assert res.headers["www-authenticate"] == "Bearer"


# ============================================================================
# Authenticated Profile (GET /api/v1/auth/me) Tests
# ============================================================================

@pytest.mark.asyncio
async def test_get_me_success(client: AsyncClient):
    """Verify /me returns the current user profile with valid Bearer token."""
    # Register & login
    await client.post(
        "/api/v1/auth/register",
        json={"email": "me.user@enterprise.com", "password": "Password123!"},
    )
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "me.user@enterprise.com", "password": "Password123!"},
    )
    token = login_res.json()["access_token"]

    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "me.user@enterprise.com"
    assert data["role"] == "employee"
    assert data["is_active"] is True
    assert "hashed_password" not in data


@pytest.mark.asyncio
async def test_get_me_missing_auth_header(client: AsyncClient):
    """Verify /me rejects requests without Authorization header."""
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.asyncio
async def test_get_me_malformed_token(client: AsyncClient):
    """Verify /me rejects malformed bearer token."""
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer not.a.valid.jwt.token"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid authentication token"


@pytest.mark.asyncio
async def test_get_me_expired_token(client: AsyncClient, test_db_session: AsyncSession):
    """Verify /me rejects expired token."""
    user = User(
        email="expired.user@enterprise.com",
        hashed_password=hash_password("Password123!"),
    )
    test_db_session.add(user)
    await test_db_session.flush()

    expired_token = create_access_token(
        subject=user.id,
        expires_delta=timedelta(seconds=-60),
    )
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Token has expired"


@pytest.mark.asyncio
async def test_get_me_nonexistent_user(client: AsyncClient):
    """Verify /me rejects valid token if user is not in database."""
    random_user_id = uuid.uuid4()
    token = create_access_token(subject=random_user_id)

    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "User account not found"


@pytest.mark.asyncio
async def test_no_auth_endpoint_returns_hashed_password(client: AsyncClient):
    """Ensure hashed_password is never exposed across registration, login, or /me."""
    reg_res = await client.post(
        "/api/v1/auth/register",
        json={"email": "safe.leak.check@enterprise.com", "password": "Password123!"},
    )
    assert "hashed_password" not in reg_res.text

    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "safe.leak.check@enterprise.com", "password": "Password123!"},
    )
    assert "hashed_password" not in login_res.text
    token = login_res.json()["access_token"]

    me_res = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert "hashed_password" not in me_res.text
