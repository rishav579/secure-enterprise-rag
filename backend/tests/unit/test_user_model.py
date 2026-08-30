import uuid
from backend.app.models.user import User, UserRole


def test_user_role_enum_values():
    """Verify UserRole enumeration definitions."""
    assert UserRole.ADMIN == "admin"
    assert UserRole.EMPLOYEE == "employee"
    assert UserRole.ADMIN.value == "admin"
    assert UserRole.EMPLOYEE.value == "employee"


def test_user_model_instantiation_defaults():
    """Verify User model field defaults upon instantiation."""
    user = User(
        email="employee@enterprise.com",
        hashed_password="secure_hashed_password_placeholder",
    )

    assert user.email == "employee@enterprise.com"
    assert user.hashed_password == "secure_hashed_password_placeholder"
    assert user.role == UserRole.EMPLOYEE
    assert user.tenant_id == "default"
    assert user.is_active is True
    # UUIDv4 primary key assigned
    assert isinstance(user.id, uuid.UUID)


def test_user_model_custom_values():
    """Verify User model custom field initialization."""
    custom_id = uuid.uuid4()
    user = User(
        id=custom_id,
        email="admin@acme.org",
        hashed_password="admin_hashed_password_placeholder",
        role=UserRole.ADMIN,
        tenant_id="tenant_acme",
        is_active=False,
    )

    assert user.id == custom_id
    assert user.email == "admin@acme.org"
    assert user.role == UserRole.ADMIN
    assert user.tenant_id == "tenant_acme"
    assert user.is_active is False
    assert repr(user) == f"<User id={custom_id} email=admin@acme.org role=UserRole.ADMIN tenant=tenant_acme>"
