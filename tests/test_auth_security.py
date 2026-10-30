"""Unit tests for Phase 2 cryptographic security: Argon2id, JWT, and tokens."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import HTTPException

from services.api.auth.security import (
    create_access_token,
    decode_access_token,
    generate_secure_token,
    hash_password,
    hash_token,
    validate_password_strength,
    verify_password,
)
from services.api.config import settings


def test_argon2id_password_hashing():
    """Verify that passwords are securely hashed with Argon2id and verified."""
    raw_pass = "SecurePass123!@#"
    hashed = hash_password(raw_pass)

    assert hashed != raw_pass
    assert hashed.startswith("$argon2id$")
    assert verify_password(raw_pass, hashed) is True
    assert verify_password("WrongPassword123!", hashed) is False


def test_password_strength_validator():
    """Verify password complexity constraints."""
    # Valid passwords
    validate_password_strength("ValidPass123!@#")
    validate_password_strength("MyComplexP@ssw0rd")

    # Too short (<8 chars)
    with pytest.raises(HTTPException) as exc:
        validate_password_strength("Short1!")
    assert exc.value.status_code == 400

    # Missing uppercase
    with pytest.raises(HTTPException) as exc:
        validate_password_strength("lowercase123!@#")
    assert exc.value.status_code == 400

    # Missing number
    with pytest.raises(HTTPException) as exc:
        validate_password_strength("NoDigitsHere!@#")
    assert exc.value.status_code == 400

    # Missing special char
    with pytest.raises(HTTPException) as exc:
        validate_password_strength("NoSpecialChar1234")
    assert exc.value.status_code == 400


def test_secure_token_generation_and_hashing():
    """Verify that refresh tokens are cryptographically random and SHA-256 hashed."""
    token1 = generate_secure_token()
    token2 = generate_secure_token()
    assert token1 != token2
    assert len(token1) >= 40

    hash1 = hash_token(token1)
    hash2 = hash_token(token2)
    assert len(hash1) == 64
    assert hash1 != hash2
    assert hash_token(token1) == hash1  # Deterministic SHA-256


def test_jwt_access_token_creation_and_decoding():
    """Verify that access tokens contain all required claims and decode successfully."""
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    role = "owner"

    token = create_access_token(user_id, tenant_id, role)
    assert isinstance(token, str)

    claims = decode_access_token(token)
    assert claims["sub"] == str(user_id)
    assert claims["tenant_id"] == str(tenant_id)
    assert claims["role"] == role
    assert claims["iss"] == settings.JWT_ISSUER
    assert claims["aud"] == settings.JWT_AUDIENCE
    assert "jti" in claims
    assert "exp" in claims
    assert "iat" in claims


def test_jwt_expired_token_rejection():
    """Verify that expired JWT tokens raise HTTP 401."""
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    # Create expired token manually
    now = datetime.now(UTC)
    expired_payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role": "employee",
        "jti": str(uuid.uuid4()),
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "iat": int((now - timedelta(minutes=30)).timestamp()),
        "exp": int((now - timedelta(minutes=15)).timestamp()),
    }
    expired_token = jwt.encode(
        expired_payload,
        settings.effective_jwt_secret,
        algorithm=settings.JWT_ALGORITHM,
    )

    with pytest.raises(HTTPException) as exc:
        decode_access_token(expired_token)
    assert exc.value.status_code == 401
    assert "expired" in exc.value.detail.lower()


def test_jwt_invalid_signature_rejection():
    """Verify that tokens signed with incorrect secret raise HTTP 401."""
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    tampered_token = jwt.encode(
        {"sub": str(user_id), "tenant_id": str(tenant_id), "role": "admin"},
        "wrong-secret-key-that-does-not-match",
        algorithm="HS256",
    )

    with pytest.raises(HTTPException) as exc:
        decode_access_token(tampered_token)
    assert exc.value.status_code == 401
    assert "invalid" in exc.value.detail.lower()


def test_jwt_malformed_token_rejection():
    """Verify that garbage strings raise HTTP 401."""
    with pytest.raises(HTTPException) as exc:
        decode_access_token("not-a-valid-jwt-token-string")
    assert exc.value.status_code == 401
