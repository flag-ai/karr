"""KARR configuration: the flag-commons base keys plus KARR's own."""

from __future__ import annotations

from typing import Any

from cryptography.fernet import Fernet
from flag_commons.config import BaseConfig, ConfigError
from flag_commons.database import normalize_url
from flag_commons.install import parse_trusted_proxies
from flag_commons.secrets import SecretNotFoundError, SecretsProvider
from pydantic import Field, SecretStr, field_validator

COMPONENT = "karr"
DEFAULT_REGISTRATION_TTL = 3600


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
    enable_hsts: bool = False

    @field_validator("registration_ttl")
    @classmethod
    def _positive_ttl(cls, value: int) -> int:
        if value <= 0:
            raise ValueError(
                "KARR_REGISTRATION_TTL must be a positive number of seconds"
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
        """Read every key through ``provider``; missing required keys are ConfigError."""
        base = cls.base_fields(COMPONENT, provider)
        base["database_url"] = SecretStr(
            normalize_url(base["database_url"].get_secret_value())
        )
        try:
            admin_token = provider.get("KARR_ADMIN_TOKEN")
            secret_key = provider.get("KARR_SECRET_KEY")
        except SecretNotFoundError as exc:
            raise ConfigError(f"config: {exc}") from exc
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
        fields: dict[str, Any] = {
            **base,
            "default_agent_url": provider.get_or_default(
                "KARR_DEFAULT_AGENT_URL", ""
            ).strip(),
            "default_agent_token": SecretStr(
                provider.get_or_default("KARR_DEFAULT_AGENT_TOKEN", "")
            ),
            "cors_origins": _split(provider.get_or_default("KARR_CORS_ORIGINS", "")),
            "admin_token": SecretStr(admin_token),
            "secret_key": SecretStr(secret_key),
            "trusted_proxies": proxies,
            "registration_ttl": ttl,
            "public_url": provider.get_or_default("KARR_PUBLIC_URL", "").strip(),
            "enable_hsts": provider.get_or_default("KARR_ENABLE_HSTS", "")
            .strip()
            .lower()
            in ("1", "true", "yes"),
        }
        try:
            return cls(**fields)
        except ValueError as exc:
            raise ConfigError(f"config: {exc}") from exc


def _split(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]
