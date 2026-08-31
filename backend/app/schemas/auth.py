import re
import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, field_validator

from backend.app.models.user import UserRole

# Standard RFC-compliant email regex pattern
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


class UserRegisterRequest(BaseModel):
    """User registration payload.
    
    Explicitly restricted to email and password only.
    Any attempt to pass role, tenant_id, or is_active is rejected.
    """
    email: str
    password: str

    model_config = ConfigDict(extra="forbid")

    @field_validator("email")
    @classmethod
    def validate_and_normalize_email(cls, v: str) -> str:
        normalized = v.strip().lower()
        if not normalized or not EMAIL_REGEX.match(normalized):
            raise ValueError("Invalid email address format.")
        return normalized

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Password cannot be blank or empty.")
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password cannot exceed 72 bytes.")
        return v


class UserLoginRequest(BaseModel):
    """User login credential payload."""
    email: str
    password: str

    model_config = ConfigDict(extra="forbid")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not v:
            raise ValueError("Password is required.")
        return v


class TokenResponse(BaseModel):
    """Bearer access token response schema."""
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """Safe user profile response representation (never includes password hashes)."""
    id: uuid.UUID
    email: str
    role: UserRole
    tenant_id: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
