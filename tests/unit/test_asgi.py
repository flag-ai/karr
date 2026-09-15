from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware


@pytest.fixture
def asgi_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[pytest.MonkeyPatch]:
    monkeypatch.setenv("DATABASE_URL", "postgres://karr:pw@db:5432/karr")
    monkeypatch.setenv("KARR_ADMIN_TOKEN", "s3cret-admin-token-0001")
    monkeypatch.setenv("KARR_SECRET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("KARR_TRUSTED_PROXIES", "10.0.0.0/8")
    for key in ("KARR_PUBLIC_URL", "OPENBAO_ADDR", "OPENBAO_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    # importing the module configures logging; keep pytest's handlers intact
    monkeypatch.setattr("karr.config.KarrConfig.setup_logging", lambda self, **kw: None)
    sys.modules.pop("karr.asgi", None)
    yield monkeypatch
    sys.modules.pop("karr.asgi", None)


def test_asgi_module_builds_the_app_with_proxy_trust(
    asgi_env: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("karr.asgi")
    assert isinstance(module.app, ProxyHeadersMiddleware)
    assert isinstance(module.app.app, FastAPI)
    assert module.config.trusted_proxies == ["10.0.0.0/8"]
