"""Unit tests for Phase 2 Pydantic schema validation."""

import pytest
from pydantic import ValidationError

from services.api.auth.schemas import LoginRequest, RegisterTenantRequest


def test_valid_register_tenant_request():
    """Verify valid tenant registration data passes schema validation."""
    payload = RegisterTenantRequest(
        company_name="Acme Corp",
        company_email="admin@acme.com",
        owner_name="Alice Owner",
        owner_email="alice@acme.com",
        password="SuperSecretPassword123!",
        country_code="US",
        timezone="America/New_York",
    )
    assert payload.country_code == "US"
    assert payload.timezone == "America/New_York"


def test_country_code_normalization():
    """Verify lowercase country codes are auto-capitalized."""
    payload = RegisterTenantRequest(
        company_name="Globex Inc",
        company_email="admin@globex.com",
        owner_name="Bob Owner",
        owner_email="bob@globex.com",
        password="SuperSecretPassword123!",
        country_code="in",  # lowercase
        timezone="Asia/Kolkata",
    )
    assert payload.country_code == "IN"


def test_invalid_country_code_rejected():
    """Verify invalid country codes raise ValidationError."""
    with pytest.raises(ValidationError):
        RegisterTenantRequest(
            company_name="Globex Inc",
            company_email="admin@globex.com",
            owner_name="Bob Owner",
            owner_email="bob@globex.com",
            password="SuperSecretPassword123!",
            country_code="USA",  # 3 chars, must be 2
            timezone="UTC",
        )


def test_invalid_timezone_rejected():
    """Verify non-existent IANA timezones are rejected."""
    with pytest.raises(ValidationError):
        RegisterTenantRequest(
            company_name="Globex Inc",
            company_email="admin@globex.com",
            owner_name="Bob Owner",
            owner_email="bob@globex.com",
            password="SuperSecretPassword123!",
            country_code="US",
            timezone="Mars/Olympus_Mons",  # Invalid
        )


def test_invalid_email_format_rejected():
    """Verify malformed email addresses are rejected."""
    with pytest.raises(ValidationError):
        RegisterTenantRequest(
            company_name="Acme Corp",
            company_email="not-an-email",
            owner_name="Alice Owner",
            owner_email="alice@acme.com",
            password="SuperSecretPassword123!",
            country_code="US",
            timezone="UTC",
        )


def test_login_request_validation():
    """Verify login request validation."""
    login = LoginRequest(
        email="user@example.com",
        password="password123",
        tenant_slug="acme-corp",
    )
    assert login.tenant_slug == "acme-corp"

    with pytest.raises(ValidationError):
        LoginRequest(
            email="invalid-email",
            password="password",
            tenant_slug="slug",
        )
