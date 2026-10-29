"""Application configuration module using pydantic-settings."""

import os

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

    @field_validator("DATABASE_URL", mode="before")
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
