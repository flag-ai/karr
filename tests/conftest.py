"""Shared fixtures for KARR tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from karr.app import create_app
from karr.config import KarrConfig

ADMIN_TOKEN = "test-admin-token-0123456789"
FERNET_KEY = Fernet.generate_key().decode()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def config() -> KarrConfig:
    return KarrConfig(
        component="karr",
        database_url=SecretStr("postgresql+psycopg://karr:pw@db/karr"),
        admin_token=SecretStr(ADMIN_TOKEN),
        secret_key=SecretStr(FERNET_KEY),
        cors_origins=["https://karr.example.com"],
    )


@pytest.fixture
def client(config: KarrConfig) -> Iterator[TestClient]:
    app = create_app(config, bootstrap=False)
    with TestClient(app, base_url="http://karr.test") as c:
        yield c


@pytest.fixture
def auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {ADMIN_TOKEN}"}
