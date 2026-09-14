"""KARR configuration: the flag-commons base keys plus KARR's own."""

from __future__ import annotations

from typing import Any

from cryptography.fernet import Fernet
from flag_commons.config import BaseConfig, ConfigError
from flag_commons.database import DatabaseError, normalize_url
from flag_commons.install import parse_trusted_proxies
from flag_commons.secrets import SecretsError, SecretsProvider
from pydantic import Field, SecretStr, field_validator

COMPONENT = "karr"
DEFAULT_REGISTRATION_TTL = 3600
MAX_REGISTRATION_TTL = 7 * 24 * 3600
MIN_ADMIN_TOKEN_LENGTH = 16


class KarrConfig(BaseConfig):
    """Everything KARR reads from its environment (or OpenBao)."""

    default_agent_url: str = ""
    default_agent_token: SecretStr = SecretStr("")
    cors_origins: list[str] = Field(default_factory=list)
    admin_token: SecretStr
    secret_key: SecretStr
    trusted_proxies: list[str] = Field(default_factory=list)
    registration_ttl: int = DEFAULT_REGISTRATION_TTL
    public_url: str = ""
    allowed_hosts: list[str] = Field(default_factory=list)
    enable_hsts: bool = False
    allow_insecure_install: bool = False

    @field_validator("registration_ttl")
    @classmethod
    def _positive_ttl(cls, value: int) -> int:
        if not 0 < value <= MAX_REGISTRATION_TTL:
            raise ValueError(
                f"KARR_REGISTRATION_TTL must be between 1 and {MAX_REGISTRATION_TTL} seconds"
            )
        return value

    @field_validator("database_url")
    @classmethod
    def _normalized_database_url(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        return SecretStr(normalize_url(raw)) if raw else value

    @field_validator("admin_token")
    @classmethod
    def _strong_admin_token(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < MIN_ADMIN_TOKEN_LENGTH:
            raise ValueError(
                f"KARR_ADMIN_TOKEN must be at least {MIN_ADMIN_TOKEN_LENGTH} characters"
            )
        return value

    @field_validator("secret_key")
    @classmethod
    def _fernet_key(cls, value: SecretStr) -> SecretStr:
        try:
            Fernet(value.get_secret_value().encode())
        except (ValueError, TypeError) as exc:
            raise ValueError("KARR_SECRET_KEY must be a Fernet key") from exc
        return value

    @classmethod
    def load(cls, provider: SecretsProvider) -> KarrConfig:
        """Read every key through ``provider``; any failure is a ConfigError."""
        try:
            return cls._load(provider)
        except ConfigError:
            raise
        except (SecretsError, DatabaseError, ValueError) as exc:
            raise ConfigError(f"config: {exc}") from exc

    @classmethod
    def _load(cls, provider: SecretsProvider) -> KarrConfig:
        base = cls.base_fields(COMPONENT, provider)
        admin_token = provider.get("KARR_ADMIN_TOKEN")
        secret_key = provider.get("KARR_SECRET_KEY")
        if not admin_token:
            raise ConfigError("config: KARR_ADMIN_TOKEN is required")
        if not secret_key:
            raise ConfigError("config: KARR_SECRET_KEY is required")
        try:
            ttl = int(
                provider.get_or_default(
                    "KARR_REGISTRATION_TTL", str(DEFAULT_REGISTRATION_TTL)
                )
            )
        except ValueError as exc:
            raise ConfigError(
                "config: KARR_REGISTRATION_TTL must be an integer"
            ) from exc
        try:
            proxies = parse_trusted_proxies(
                provider.get_or_default("KARR_TRUSTED_PROXIES", "")
            )
        except ValueError as exc:
            raise ConfigError(f"config: KARR_TRUSTED_PROXIES: {exc}") from exc
        origins = _split(provider.get_or_default("KARR_CORS_ORIGINS", ""))
        if "*" in origins:
            raise ConfigError(
                "config: KARR_CORS_ORIGINS must list explicit origins, not *"
            )
        fields: dict[str, Any] = {
            **base,
            "default_agent_url": provider.get_or_default(
                "KARR_DEFAULT_AGENT_URL", ""
            ).strip(),
            "default_agent_token": SecretStr(
                provider.get_or_default("KARR_DEFAULT_AGENT_TOKEN", "")
            ),
            "cors_origins": origins,
            "admin_token": SecretStr(admin_token),
            "secret_key": SecretStr(secret_key),
            "trusted_proxies": proxies,
            "registration_ttl": ttl,
            "public_url": provider.get_or_default("KARR_PUBLIC_URL", "").strip(),
            "allowed_hosts": _split(provider.get_or_default("KARR_ALLOWED_HOSTS", "")),
            "enable_hsts": _truthy(provider.get_or_default("KARR_ENABLE_HSTS", "")),
            "allow_insecure_install": _truthy(
                provider.get_or_default("KARR_ALLOW_INSECURE_INSTALL", "")
            ),
        }
        return cls(**fields)


def _truthy(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes")


def _split(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]
