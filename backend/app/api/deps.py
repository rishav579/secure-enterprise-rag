import uuid
from typing import AsyncGenerator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.security import TokenExpiredError, TokenInvalidError, decode_access_token
from backend.app.database import get_db
from backend.app.models.user import User, UserRole

# OAuth2 scheme with auto_error=False to allow explicit custom error responses and headers
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
    auto_error=False,
)


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Validate bearer token and resolve the active User identity from the database.
    
    Security failures consistently map to HTTP 401 with standard WWW-Authenticate headers.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(token)
    except TokenExpiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except TokenInvalidError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    sub = payload.get("sub")
    try:
        user_id = uuid.UUID(sub)
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def require_role(*roles: UserRole):
    """FastAPI dependency factory enforcing that the authenticated user possesses one of the required roles.
    
    Raises HTTP 403 Forbidden if user privileges are insufficient.
    """
    allowed_roles = set(roles)

    async def _role_dependency(current_user: User = Depends(get_current_user)) -> User:
        from backend.app.core.permissions import check_role
        check_role(current_user, allowed_roles)
        return current_user

    return _role_dependency


# Convenience dependency requiring administrator privileges
require_admin = require_role(UserRole.ADMIN)


def verify_tenant_access(current_user: User, target_tenant_id: str) -> None:
    """Verify that the target tenant scope matches the authenticated user's authoritative tenant_id.
    
    Raises HTTP 403 Forbidden on tenant mismatch.
    """
    from backend.app.core.permissions import check_tenant
    check_tenant(current_user, target_tenant_id)


def get_storage_service():
    from backend.app.services.storage import LocalStorageService
    settings = get_settings()
    return LocalStorageService(base_dir=settings.STORAGE_LOCAL_DIR)


def get_embedding_service():
    from backend.app.services.embedding import GeminiEmbeddingService, MockEmbeddingService
    settings = get_settings()
    if settings.GEMINI_API_KEY:
        return GeminiEmbeddingService(
            api_key=settings.GEMINI_API_KEY.get_secret_value(),
            model_name=settings.EMBEDDING_MODEL,
            dimension=settings.EMBEDDING_DIMENSIONS,
            batch_size=settings.EMBEDDING_BATCH_SIZE,
        )
    return MockEmbeddingService(dimension=settings.EMBEDDING_DIMENSIONS)


__all__ = [
    "get_db",
    "oauth2_scheme",
    "get_current_user",
    "require_role",
    "require_admin",
    "verify_tenant_access",
    "get_storage_service",
    "get_embedding_service",
]

