import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.user import User, UserRole


@pytest.mark.asyncio
async def test_create_and_query_user(test_db_session: AsyncSession):
    """Verify user persistence, retrieval, and fields in database."""
    user = User(
        email="test.user@enterprise.internal",
        hashed_password="dummy_hash_for_test",
        role=UserRole.EMPLOYEE,
        tenant_id="tenant_alpha",
    )
    test_db_session.add(user)
    await test_db_session.flush()

    stmt = select(User).where(User.email == "test.user@enterprise.internal")
    result = await test_db_session.execute(stmt)
    persisted_user = result.scalar_one_or_none()

    assert persisted_user is not None
    assert persisted_user.id == user.id
    assert persisted_user.email == "test.user@enterprise.internal"
    assert persisted_user.role == UserRole.EMPLOYEE
    assert persisted_user.tenant_id == "tenant_alpha"
    assert persisted_user.is_active is True
    assert persisted_user.created_at is not None


@pytest.mark.asyncio
async def test_user_email_unique_constraint(test_db_session: AsyncSession):
    """Verify that duplicate emails violate unique constraint and raise IntegrityError."""
    user1 = User(
        email="unique.email@enterprise.internal",
        hashed_password="hash_1",
        role=UserRole.EMPLOYEE,
        tenant_id="tenant_alpha",
    )
    test_db_session.add(user1)
    await test_db_session.flush()

    user2 = User(
        email="unique.email@enterprise.internal",  # Duplicate email
        hashed_password="hash_2",
        role=UserRole.ADMIN,
        tenant_id="tenant_beta",
    )
    test_db_session.add(user2)

    with pytest.raises(IntegrityError):
        await test_db_session.flush()

    await test_db_session.rollback()


@pytest.mark.asyncio
async def test_user_tenant_and_role_query(test_db_session: AsyncSession):
    """Verify composite tenant and role filtering."""
    admin_user = User(
        email="admin@tenant1.com",
        hashed_password="hash",
        role=UserRole.ADMIN,
        tenant_id="tenant_1",
    )
    employee_user1 = User(
        email="emp1@tenant1.com",
        hashed_password="hash",
        role=UserRole.EMPLOYEE,
        tenant_id="tenant_1",
    )
    employee_user2 = User(
        email="emp2@tenant2.com",
        hashed_password="hash",
        role=UserRole.EMPLOYEE,
        tenant_id="tenant_2",
    )
    test_db_session.add_all([admin_user, employee_user1, employee_user2])
    await test_db_session.flush()

    # Query only employees in tenant_1
    stmt = select(User).where(
        User.tenant_id == "tenant_1",
        User.role == UserRole.EMPLOYEE,
    )
    result = await test_db_session.execute(stmt)
    tenant1_employees = result.scalars().all()

    assert len(tenant1_employees) == 1
    assert tenant1_employees[0].email == "emp1@tenant1.com"
