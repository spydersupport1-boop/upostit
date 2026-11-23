"""Application configuration module using pydantic-settings."""

import os
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ENVIRONMENT: str = Field(default="development")
    LOG_LEVEL: str = Field(default="info")
    SECRET_KEY: str = Field(default="change-this-insecure-default-key-32-chars-min")
    API_PORT: int = Field(default=8000)
    API_HOST: str = Field(default="0.0.0.0")

    # Supabase Project Credentials
    SUPABASE_URL: str = Field(default="")
    SUPABASE_PROJECT_REF: str = Field(default="")
    SUPABASE_ANON_KEY: str = Field(default="")
    SUPABASE_SERVICE_ROLE_KEY: str = Field(default="")

    # Supabase PostgreSQL Connection
    DATABASE_URL: str = Field(default="")
    DB_POOL_SIZE: int = Field(default=10)
    DB_MAX_OVERFLOW: int = Field(default=5)
    DB_POOL_TIMEOUT: int = Field(default=30)
    DB_ECHO: bool = Field(default=False)

    # Redis Cache & Queue
    REDIS_URL: str = Field(default="redis://localhost:6379/0")
    CELERY_BROKER_URL: str = Field(default="redis://localhost:6379/1")
    CELERY_RESULT_BACKEND: str = Field(default="redis://localhost:6379/2")

    # Storage
    STORAGE_ENDPOINT: str = Field(default="http://localhost:9000")
    STORAGE_ACCESS_KEY: str = Field(default="placeholder_access_key")
    STORAGE_SECRET_KEY: str = Field(default="placeholder_secret_key")
    STORAGE_BUCKET: str = Field(default="attendance-assets")
    STORAGE_USE_SSL: bool = Field(default=False)
    STORAGE_ALLOW_MEMORY_FALLBACK: bool = Field(
        default=True,
        description="Allow in-memory object fallback only in development/test environments.",
    )

    # Authentication & Security (Phase 2)
    JWT_SECRET_KEY: str = Field(default="")
    JWT_ALGORITHM: str = Field(default="HS256")
    JWT_ISSUER: str = Field(default="attendance-saas")
    JWT_AUDIENCE: str = Field(default="attendance-app")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=15)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7)
    CORS_ALLOWED_ORIGINS: list[str] = Field(
        default=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]
    )
    COOKIE_SECURE: bool = Field(default=False)
    COOKIE_SAMESITE: Literal["lax", "strict", "none"] = Field(default="lax")
    COOKIE_DOMAIN: str | None = Field(default=None)

    # Database Security & RLS Execution (Phase 2)
    MIGRATION_DATABASE_URL: str = Field(default="")
    RUNTIME_DATABASE_ROLE: str = Field(default="authenticated")

    # Frontend Web App URL
    FRONTEND_URL: str = Field(default="http://localhost:3000")

    # Employee Invitations & Account Activation (Phase 4 Milestone 4)
    INVITATION_TOKEN_EXPIRE_HOURS: int = Field(default=168)  # 7 days
    EMAIL_BACKEND: str = Field(default="console")  # console, smtp, memory
    SMTP_HOST: str = Field(default="")
    SMTP_PORT: int = Field(default=587)
    SMTP_USER: str = Field(default="")
    SMTP_PASSWORD: str = Field(default="")
    SMTP_USE_TLS: bool = Field(default=True)
    EMAIL_FROM_ADDRESS: str = Field(default="noreply@attendance.io")
    EMAIL_FROM_NAME: str = Field(default="Attendance SaaS")

    # Phase 10 Notification & FCM Push Configuration
    PUSH_TOKEN_ENCRYPTION_KEY: str = Field(
        default="",
        description="URL-safe base64-encoded 32-byte key for Fernet authenticated encryption.",
    )
    FIREBASE_CREDENTIALS_PATH: str = Field(
        default="",
        description="Filesystem path to Firebase service-account JSON file.",
    )
    FIREBASE_CREDENTIALS_JSON: str = Field(
        default="",
        description="Raw JSON string of Firebase service-account credentials.",
    )
    FIREBASE_PROJECT_ID: str = Field(
        default="",
        description="Optional Google Cloud / Firebase Project ID.",
    )
    FCM_ENABLED: bool = Field(
        default=False,
        description="Flag enabling live FCM delivery (requires valid credentials).",
    )

    @property
    def effective_jwt_secret(self) -> str:
        """Returns the configured JWT_SECRET_KEY, falling back to SECRET_KEY."""
        return self.JWT_SECRET_KEY if self.JWT_SECRET_KEY else self.SECRET_KEY

    @field_validator("DATABASE_URL", "MIGRATION_DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: str) -> str:
        if not v:
            return ""
        # Automatically ensure asyncpg driver is specified for async SQLAlchemy
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        if v.startswith("postgresql://") and not v.startswith("postgresql+asyncpg://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v


settings = Settings()
