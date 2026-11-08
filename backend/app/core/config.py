"""Typed application settings loaded from environment variables."""

from functools import lru_cache
from typing import Any

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration; secrets are never given implicit defaults."""

    app_name: str = "GigBridge API"
    app_env: str = "development"
    debug: bool = False
    database_url: SecretStr = Field(description="Async SQLAlchemy PostgreSQL URL.")
    frontend_url: str = "http://localhost:3000"
    jwt_secret_key: SecretStr = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=30, ge=1)
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @classmethod
    def _normalize_debug(cls, value: Any) -> Any:
        """Accept deployment labels in addition to conventional boolean values."""

        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "production", "prod"}:
                return False
            if normalized in {"debug", "development", "dev"}:
                return True
        return value

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug(cls, value: Any) -> Any:
        return cls._normalize_debug(value)

    @field_validator("jwt_secret_key")
    @classmethod
    def reject_placeholder_jwt_secret(cls, value: SecretStr) -> SecretStr:
        """Fail fast when an example placeholder was copied into runtime config."""

        secret = value.get_secret_value().lower()
        if any(marker in secret for marker in ("replace", "change-me", "example")):
            raise ValueError("JWT_SECRET_KEY must be replaced with a private random value.")
        return value

@lru_cache
def get_settings() -> Settings:
    """Return cached settings for the current process."""

    return Settings()
