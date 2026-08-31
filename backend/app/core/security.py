import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Union

import bcrypt
import jwt

from backend.app.config import get_settings

BCRYPT_MAX_PASSWORD_BYTES = 72
BCRYPT_SALT_ROUNDS = 12


class TokenError(Exception):
    """Base exception for all token-related security failures."""
    pass


class TokenExpiredError(TokenError):
    """Raised when an authentication token has expired."""
    pass


class TokenInvalidError(TokenError):
    """Raised when an authentication token is invalid, tampered with, or malformed."""
    pass


def hash_password(password: str) -> str:
    """Hash a plaintext password securely using direct bcrypt.
    
    Enforces a strict 72-byte length boundary to prevent silent truncation attacks.
    """
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > BCRYPT_MAX_PASSWORD_BYTES:
        raise ValueError(
            f"Password exceeds maximum length of {BCRYPT_MAX_PASSWORD_BYTES} bytes."
        )

    salt = bcrypt.gensalt(rounds=BCRYPT_SALT_ROUNDS)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash in constant time.
    
    Returns False if inputs are malformed, corrupted, or exceed byte boundaries,
    ensuring robust resilience against crash/oracle attacks.
    """
    try:
        plain_bytes = plain_password.encode("utf-8")
        if len(plain_bytes) > BCRYPT_MAX_PASSWORD_BYTES:
            return False

        hashed_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(plain_bytes, hashed_bytes)
    except (ValueError, TypeError, Exception):
        # Corrupted hash format, invalid encoding, or type mismatch safely returns False
        return False


def create_access_token(
    subject: Union[str, uuid.UUID],
    expires_delta: Union[timedelta, None] = None,
) -> str:
    """Generate a signed JWT access token with a minimal payload (sub, iat, exp)."""
    settings = get_settings()

    now_utc = datetime.now(timezone.utc)
    if expires_delta is not None:
        expire_utc = now_utc + expires_delta
    else:
        expire_utc = now_utc + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: Dict[str, Any] = {
        "sub": str(subject),
        "iat": int(now_utc.timestamp()),
        "exp": int(expire_utc.timestamp()),
    }

    token = jwt.encode(
        payload=payload,
        key=settings.SECRET_KEY.get_secret_value(),
        algorithm=settings.ALGORITHM,
    )
    return token


def decode_access_token(token: str) -> Dict[str, Any]:
    """Verify and decode a signed JWT access token.
    
    Enforces signature validation, expiration, and presence of minimal claims (sub, iat, exp).
    Raises TokenExpiredError or TokenInvalidError on verification failures.
    """
    settings = get_settings()

    try:
        payload = jwt.decode(
            jwt=token,
            key=settings.SECRET_KEY.get_secret_value(),
            algorithms=[settings.ALGORITHM],
            options={
                "require": ["sub", "iat", "exp"],
                "verify_signature": True,
                "verify_exp": True,
                "verify_iat": True,
            },
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError("Access token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenInvalidError("Access token is invalid or corrupted.") from exc
    except Exception as exc:
        raise TokenInvalidError("Failed to decode access token.") from exc

    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        raise TokenInvalidError("Access token subject claim is missing or empty.")

    return payload
