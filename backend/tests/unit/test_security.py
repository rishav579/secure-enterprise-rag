import time
import uuid
from datetime import timedelta
import jwt
import pytest

from backend.app.config import get_settings
from backend.app.core.security import (
    TokenError,
    TokenExpiredError,
    TokenInvalidError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

settings = get_settings()


# ============================================================================
# Password Hashing & Verification Tests
# ============================================================================

def test_hash_password_creates_valid_bcrypt_hash():
    """Verify password hashing produces standard bcrypt format."""
    password = "CorrectHorseBatteryStaple123!"
    hashed = hash_password(password)

    assert isinstance(hashed, str)
    assert hashed.startswith("$2b$")
    assert hashed != password


def test_verify_password_success():
    """Verify correct password matches its hash."""
    password = "MySecureEnterprisePassword2026#"
    hashed = hash_password(password)

    assert verify_password(password, hashed) is True


def test_verify_password_incorrect():
    """Verify wrong password fails verification."""
    password = "MySecureEnterprisePassword2026#"
    hashed = hash_password(password)

    assert verify_password("WrongPassword123!", hashed) is False
    assert verify_password("", hashed) is False


def test_hash_password_unique_salts():
    """Verify repeated hashing of the same password generates distinct hashes (unique salts)."""
    password = "IdenticalPasswordToHash"
    hash1 = hash_password(password)
    hash2 = hash_password(password)

    assert hash1 != hash2
    assert verify_password(password, hash1) is True
    assert verify_password(password, hash2) is True


def test_hash_password_72_byte_limit():
    """Verify passwords exceeding bcrypt's 72-byte limit raise an explicit ValueError."""
    long_password = "A" * 73
    with pytest.raises(ValueError, match="Password exceeds maximum length of 72 bytes"):
        hash_password(long_password)


def test_verify_password_72_byte_limit_safe():
    """Verify verification safely returns False when plain password exceeds 72 bytes."""
    hashed = hash_password("ValidPassword")
    long_password = "A" * 73
    assert verify_password(long_password, hashed) is False


def test_verify_password_malformed_hash_safe():
    """Verify verification returns False gracefully when presented with corrupted hashes."""
    assert verify_password("AnyPassword", "invalid_not_a_bcrypt_hash") is False
    assert verify_password("AnyPassword", "$2b$12$corrupted_and_truncated_hash") is False
    assert verify_password("AnyPassword", "") is False


# ============================================================================
# JWT Creation & Verification Tests
# ============================================================================

def test_create_and_decode_access_token_with_string_subject():
    """Verify access token creation and decoding with a string subject."""
    subject = "user@enterprise.internal"
    token = create_access_token(subject=subject)

    assert isinstance(token, str)
    payload = decode_access_token(token)

    assert payload["sub"] == subject
    assert "exp" in payload
    assert "iat" in payload
    assert payload["exp"] > payload["iat"]


def test_create_and_decode_access_token_with_uuid_subject():
    """Verify access token creation and decoding with a UUID subject."""
    user_id = uuid.uuid4()
    token = create_access_token(subject=user_id)

    payload = decode_access_token(token)
    assert payload["sub"] == str(user_id)


def test_token_expiration_custom_delta():
    """Verify token expiration matches custom delta."""
    subject = "temp-user"
    token = create_access_token(subject=subject, expires_delta=timedelta(minutes=15))
    payload = decode_access_token(token)

    # Expected expiration difference is approximately 15 minutes (900 seconds)
    duration = payload["exp"] - payload["iat"]
    assert duration == 900


def test_decode_access_token_expired():
    """Verify expired token raises TokenExpiredError."""
    subject = "expired-user"
    # Create token that expired 10 seconds ago
    token = create_access_token(subject=subject, expires_delta=timedelta(seconds=-10))

    with pytest.raises(TokenExpiredError, match="Access token has expired"):
        decode_access_token(token)


def test_decode_access_token_invalid_signature():
    """Verify token signed with an untrusted secret raises TokenInvalidError."""
    untrusted_secret = "different-secret-key-that-does-not-match-settings-32bytes!"
    forged_token = jwt.encode(
        payload={"sub": "attacker", "iat": int(time.time()), "exp": int(time.time()) + 3600},
        key=untrusted_secret,
        algorithm=settings.ALGORITHM,
    )

    with pytest.raises(TokenInvalidError, match="Access token is invalid or corrupted"):
        decode_access_token(forged_token)


def test_decode_access_token_tampered():
    """Verify token whose payload or signature has been tampered with raises TokenInvalidError."""
    token = create_access_token(subject="legit-user")
    parts = token.split(".")
    # Tamper with the signature portion
    tampered_token = f"{parts[0]}.{parts[1]}.tampered_signature"

    with pytest.raises(TokenInvalidError):
        decode_access_token(tampered_token)


def test_decode_access_token_malformed_string():
    """Verify malformed non-JWT strings raise TokenInvalidError."""
    with pytest.raises(TokenInvalidError):
        decode_access_token("this.is.not.a.valid.jwt")
    with pytest.raises(TokenInvalidError):
        decode_access_token("random_garbage_string")


def test_decode_access_token_missing_required_claims():
    """Verify tokens missing required sub, exp, or iat claims raise TokenInvalidError."""
    secret = settings.SECRET_KEY.get_secret_value()

    # Missing 'sub'
    token_no_sub = jwt.encode(
        payload={"iat": int(time.time()), "exp": int(time.time()) + 3600},
        key=secret,
        algorithm=settings.ALGORITHM,
    )
    with pytest.raises(TokenInvalidError):
        decode_access_token(token_no_sub)

    # Missing 'exp'
    token_no_exp = jwt.encode(
        payload={"sub": "user123", "iat": int(time.time())},
        key=secret,
        algorithm=settings.ALGORITHM,
    )
    with pytest.raises(TokenInvalidError):
        decode_access_token(token_no_exp)

    # Empty 'sub'
    token_empty_sub = jwt.encode(
        payload={"sub": "   ", "iat": int(time.time()), "exp": int(time.time()) + 3600},
        key=secret,
        algorithm=settings.ALGORITHM,
    )
    with pytest.raises(TokenInvalidError, match="Access token subject claim is missing or empty"):
        decode_access_token(token_empty_sub)


# ============================================================================
# Secret Exposure Defense Tests
# ============================================================================

def test_secret_never_exposed_in_token_or_payload():
    """Verify that the raw secret key is never leaked in token components or exceptions."""
    secret = settings.SECRET_KEY.get_secret_value()
    token = create_access_token(subject="user_secret_check")

    # Secret must never be in the token string
    assert secret not in token

    # Secret must not appear in the decoded payload
    payload = decode_access_token(token)
    assert secret not in str(payload)

    # Secret must not appear in token unverified headers/payload
    unverified_header = jwt.get_unverified_header(token)
    assert secret not in str(unverified_header)


def test_exceptions_do_not_leak_secret():
    """Verify security exception strings do not expose secret keys."""
    secret = settings.SECRET_KEY.get_secret_value()

    expired_token = create_access_token(subject="test", expires_delta=timedelta(seconds=-1))
    try:
        decode_access_token(expired_token)
    except TokenExpiredError as exc:
        assert secret not in str(exc)

    try:
        decode_access_token("corrupted.token.value")
    except TokenInvalidError as exc:
        assert secret not in str(exc)
