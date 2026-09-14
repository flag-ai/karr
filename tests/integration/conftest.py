"""Integration tests need a live PostgreSQL in TEST_DATABASE_URL."""

from __future__ import annotations

import os

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from karr.config import KarrConfig


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    return url


@pytest.fixture
def live_config(database_url: str) -> KarrConfig:
    return KarrConfig(
        component="karr",
        database_url=SecretStr(database_url),
        admin_token=SecretStr("integration-admin-token"),
        secret_key=SecretStr(Fernet.generate_key().decode()),
    )
