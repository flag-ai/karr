from __future__ import annotations

import importlib
import sys

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI


def test_asgi_module_builds_the_app_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgres://karr:pw@db:5432/karr")
    monkeypatch.setenv("KARR_ADMIN_TOKEN", "s3cret-admin-token-0001")
    monkeypatch.setenv("KARR_SECRET_KEY", Fernet.generate_key().decode())
    monkeypatch.delenv("KARR_PUBLIC_URL", raising=False)
    sys.modules.pop("karr.asgi", None)
    module = importlib.import_module("karr.asgi")
    assert isinstance(module.app, FastAPI)
    assert module.config.component == "karr"
