import logging
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_current_user, get_db
from backend.app.core.security import create_access_token, hash_password, verify_password
from backend.app.core.rate_limit import limiter
from backend.app.models.user import User, UserRole
from backend.app.schemas.auth import TokenResponse, UserLoginRequest, UserRegisterRequest, UserResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new employee user account",
)
@limiter.limit("5/minute")
async def register(
    request: Request,
    body: UserRegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Register a new user account with default Employee privileges.
    
    Email is normalized to lowercase. Passwords are validated and hashed securely.
    Privilege escalation is strictly forbidden (role and tenant cannot be client-specified).
    """
    stmt = select(User).where(User.email == body.email)
    result = await db.execute(stmt)
    existing_user = result.scalar_one_or_none()

    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists.",
        )

    hashed_pw = hash_password(body.password)

    new_user = User(
        email=body.email,
        hashed_password=hashed_pw,
        role=UserRole.EMPLOYEE,
        tenant_id="default",
        is_active=True,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    logger.info("Successfully registered new user account with default employee role")
    return UserResponse.model_validate(new_user)


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate user and issue JWT access token",
)
@limiter.limit("5/minute")
async def login(
    request: Request,
    body: UserLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticate credentials and generate a signed access token.
    
    Enforces strict anti-enumeration: unknown email, invalid password, and inactive
    accounts return the exact same HTTP 401 response with 'Invalid email or password'.
    """
    stmt = select(User).where(User.email == body.email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    # Uniform authentication rejection helper
    def _unauthorized_error():
        logger.info("Authentication rejected: invalid credentials")
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Valid bcrypt hash for constant-time comparison when user is not found
    _DUMMY_HASH = "$2b$12$e8pS4.e2hG3uA7rL9wE5zeO5Z9h7e3k5r6k7e8k9r0k1r2k3r4k5e"
    
    target_hash = user.hashed_password if user else _DUMMY_HASH
    valid_pw = verify_password(body.password, target_hash)
    
    if user is None or not valid_pw or not user.is_active:
        raise _unauthorized_error()

    token = create_access_token(subject=user.id)
    return TokenResponse(access_token=token, token_type="bearer")


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve authenticated user profile",
)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Return the profile for the currently authenticated user.
    
    Protected by get_current_user dependency. Excludes password hash.
    """
    return UserResponse.model_validate(current_user)
