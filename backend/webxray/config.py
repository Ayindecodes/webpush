"""Runtime configuration. Every value can be overridden with a WEBXRAY_* env var."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]

# Development-only defaults. Production refuses to start with these.
_DEV_SECRET_KEY = "dev-insecure-change-me-dev-insecure-change-me"
_DEV_CREDENTIAL_KEY = "Wn0ZS0qJm9l3w6fW2r2bEw2nB1Hk0xY5uVd7cQe4aTg="


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WEBXRAY_",
        env_file=(REPO_ROOT / ".env", REPO_ROOT / "backend" / ".env"),
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"

    database_url: str = "postgresql+asyncpg://webxray:webxray_dev_password@127.0.0.1:55432/webxray"
    redis_url: str = "redis://127.0.0.1:56379/0"

    # HMAC key for session tokens and short-lived evidence links.
    secret_key: str = Field(default=_DEV_SECRET_KEY, min_length=32)
    # Fernet key (urlsafe base64, 32 bytes) used to encrypt stored test credentials.
    credential_encryption_key: str = _DEV_CREDENTIAL_KEY

    artifact_dir: Path = REPO_ROOT / ".data" / "artifacts"
    runner_dir: Path = REPO_ROOT / "runner"

    # Exact origins (scheme://host:port) an operator explicitly allows even though
    # they resolve to loopback/private addresses. Used for local benchmark apps.
    # Empty in production unless the operator deliberately opts in.
    allowed_private_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # Origins allowed to make state-changing requests to the API (CSRF defence).
    allowed_web_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    cookie_secure: bool = False
    session_ttl_hours: int = 24 * 7
    evidence_link_ttl_seconds: int = 600

    # Worker
    worker_lease_seconds: int = 60
    worker_poll_seconds: float = 5.0
    browser_headless: bool = True
    egress_allowed_ports: Annotated[list[int], NoDecode] = Field(default_factory=lambda: [80, 443, 8080, 8443])

    test_identity_email_domain: str = "example.test"

    log_level: str = "INFO"

    @field_validator("allowed_private_origins", "allowed_web_origins", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    @model_validator(mode="after")
    def _no_dev_secrets_in_production(self) -> Settings:
        if self.environment == "production":
            if self.secret_key == _DEV_SECRET_KEY or self.credential_encryption_key == _DEV_CREDENTIAL_KEY:
                raise ValueError("Set WEBXRAY_SECRET_KEY and WEBXRAY_CREDENTIAL_ENCRYPTION_KEY in production")
            if not self.cookie_secure:
                raise ValueError("WEBXRAY_COOKIE_SECURE must be true in production")
        return self

    @field_validator("egress_allowed_ports", mode="before")
    @classmethod
    def _split_ports(cls, v: object) -> object:
        if isinstance(v, str):
            return [int(item) for item in v.split(",") if item.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
