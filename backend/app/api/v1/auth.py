import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_current_user, get_db
from backend.app.core.security import create_access_token, hash_password, verify_password
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
async def register(
    request: UserRegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Register a new user account with default Employee privileges.
    
    Email is normalized to lowercase. Passwords are validated and hashed securely.
    Privilege escalation is strictly forbidden (role and tenant cannot be client-specified).
    """
    stmt = select(User).where(User.email == request.email)
    result = await db.execute(stmt)
    existing_user = result.scalar_one_or_none()

    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists.",
        )

    hashed_pw = hash_password(request.password)

    new_user = User(
        email=request.email,
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
async def login(
    request: UserLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticate credentials and generate a signed access token.
    
    Enforces strict anti-enumeration: unknown email, invalid password, and inactive
    accounts return the exact same HTTP 401 response with 'Invalid email or password'.
    """
    stmt = select(User).where(User.email == request.email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    # Uniform authentication rejection helper
    def _unauthorized_error(diagnostic_reason: str):
        logger.info(f"Authentication rejected: {diagnostic_reason}")
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user is None:
        raise _unauthorized_error("unknown email")

    if not verify_password(request.password, user.hashed_password):
        raise _unauthorized_error("incorrect password")

    if not user.is_active:
        raise _unauthorized_error("inactive account")

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
