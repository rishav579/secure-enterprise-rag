import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.security import hash_password, verify_password
from backend.app.models.user import User, UserRole
from backend.scripts.bootstrap_admin import run_bootstrap


@pytest.mark.asyncio
async def test_bootstrap_admin_missing_credentials():
    """Verify that bootstrap fails if email or password is empty."""
    res1 = await run_bootstrap(email="", password="SomePassword123!")
    assert res1 is False

    res2 = await run_bootstrap(email="admin@corp.internal", password="")
    assert res2 is False


@pytest.mark.asyncio
async def test_bootstrap_admin_creation_and_idempotency(test_db_session: AsyncSession):
    """Verify fresh admin creation and idempotent execution."""
    email = "bootstrap.admin@enterprise.internal"
    password = "AdminSecurePassword123!"

    # 1. First execution: creates user
    success1 = await run_bootstrap(email=email, password=password, tenant_id="tenant_prod", session=test_db_session)
    assert success1 is True

    stmt = select(User).where(User.email == email)
    res = await test_db_session.execute(stmt)
    user = res.scalar_one_or_none()

    assert user is not None
    assert user.email == email
    assert user.role == UserRole.ADMIN
    assert user.tenant_id == "tenant_prod"
    assert user.is_active is True
    assert verify_password(password, user.hashed_password) is True

    # 2. Second execution (idempotent no-op): succeeds without error
    success2 = await run_bootstrap(email=email, password=password, tenant_id="tenant_prod", session=test_db_session)
    assert success2 is True

    res2 = await test_db_session.execute(stmt)
    users = res2.scalars().all()
    assert len(users) == 1


@pytest.mark.asyncio
async def test_bootstrap_admin_promote_existing_employee(test_db_session: AsyncSession):
    """Verify promoting an existing employee user to admin."""
    email = "employee.to.admin@enterprise.internal"
    user = User(
        email=email,
        hashed_password=hash_password("OldPassword123!"),
        role=UserRole.EMPLOYEE,
        tenant_id="default",
    )
    test_db_session.add(user)
    await test_db_session.commit()

    # Run bootstrap for existing employee email
    new_password = "NewAdminPassword123!"
    success = await run_bootstrap(email=email, password=new_password, session=test_db_session)
    assert success is True

    await test_db_session.refresh(user)
    assert user.role == UserRole.ADMIN
    assert verify_password(new_password, user.hashed_password) is True

