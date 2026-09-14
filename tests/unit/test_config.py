from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from flag_commons.config import ConfigError
from flag_commons.secrets import EnvProvider

from karr.config import KarrConfig

KEY = Fernet.generate_key().decode()


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for k in list(dict(__import__("os").environ)):
        if k.startswith("KARR_") or k in (
            "DATABASE_URL",
            "LOG_LEVEL",
            "LOG_FORMAT",
            "LISTEN_ADDR",
        ):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgres://karr:pw@db:5432/karr")
    monkeypatch.setenv("KARR_ADMIN_TOKEN", "s3cret-admin-token-0001")
    monkeypatch.setenv("KARR_SECRET_KEY", KEY)
    return monkeypatch


def test_load_defaults(env: pytest.MonkeyPatch) -> None:
    cfg = KarrConfig.load(EnvProvider())
    assert cfg.component == "karr"
    assert (
        cfg.database_url.get_secret_value()
        == "postgresql+psycopg://karr:pw@db:5432/karr"
    )
    assert cfg.listen_addr == ":8080" and cfg.bind_address() == ("0.0.0.0", 8080)
    assert cfg.registration_ttl == 3600
    assert cfg.cors_origins == [] and cfg.trusted_proxies == []
    assert cfg.enable_hsts is False
    assert "s3cret-admin-token" not in repr(cfg) and KEY not in repr(cfg)
    assert cfg.admin_token.get_secret_value() == "s3cret-admin-token-0001"


def test_load_custom(env: pytest.MonkeyPatch) -> None:
    env.setenv("KARR_CORS_ORIGINS", "https://a.example, https://b.example")
    env.setenv("KARR_TRUSTED_PROXIES", "10.0.0.0/8, 192.168.1.1")
    env.setenv("KARR_REGISTRATION_TTL", "120")
    env.setenv("KARR_DEFAULT_AGENT_URL", " http://gpu-01:7777 ")
    env.setenv("KARR_DEFAULT_AGENT_TOKEN", "t")
    env.setenv("KARR_PUBLIC_URL", "https://karr.example.com")
    env.setenv("KARR_ENABLE_HSTS", "true")
    cfg = KarrConfig.load(EnvProvider())
    assert cfg.cors_origins == ["https://a.example", "https://b.example"]
    assert cfg.trusted_proxies == ["10.0.0.0/8", "192.168.1.1"]
    assert cfg.registration_ttl == 120
    assert cfg.default_agent_url == "http://gpu-01:7777"
    assert cfg.default_agent_token.get_secret_value() == "t"
    assert cfg.public_url == "https://karr.example.com"
    assert cfg.enable_hsts is True


@pytest.mark.parametrize(
    ("key", "value", "match"),
    [
        ("KARR_ADMIN_TOKEN", "", "KARR_ADMIN_TOKEN"),
        ("KARR_SECRET_KEY", "", "KARR_SECRET_KEY"),
        ("KARR_SECRET_KEY", "not-a-fernet-key", "Fernet"),
        ("KARR_REGISTRATION_TTL", "abc", "integer"),
        ("KARR_REGISTRATION_TTL", "0", "positive"),
        ("KARR_TRUSTED_PROXIES", "10.0.0/8", "TRUSTED_PROXIES"),
        ("DATABASE_URL", "mysql://x", "invalid connection string"),
    ],
)
def test_load_rejects(
    env: pytest.MonkeyPatch, key: str, value: str, match: str
) -> None:
    env.setenv(key, value)
    with pytest.raises((ConfigError, Exception), match=match):
        KarrConfig.load(EnvProvider())


def test_database_url_is_normalized_on_direct_construction() -> None:
    from cryptography.fernet import Fernet
    from pydantic import SecretStr

    cfg = KarrConfig(
        component="karr",
        database_url=SecretStr("postgres://k:p@db/karr"),
        admin_token=SecretStr("an-admin-token-that-is-long"),
        secret_key=SecretStr(Fernet.generate_key().decode()),
    )
    assert cfg.database_url.get_secret_value() == "postgresql+psycopg://k:p@db/karr"


def test_missing_required(env: pytest.MonkeyPatch) -> None:
    env.delenv("KARR_ADMIN_TOKEN")
    with pytest.raises(ConfigError, match="KARR_ADMIN_TOKEN"):
        KarrConfig.load(EnvProvider())
