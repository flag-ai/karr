"""Integration tests need a live PostgreSQL in TEST_DATABASE_URL."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from flag_commons.database import create_sync_engine
from pydantic import SecretStr
from sqlalchemy import text

from karr.app import create_app
from karr.config import KarrConfig

ADMIN = "integration-admin-token-0001"


@pytest.fixture(scope="session")
def database_url() -> str:
    """The disposable test database; every KARR table is dropped at session start.

    A database that once ran Go KARR still holds golang-migrate's tables, which
    the Alembic baseline cannot adopt (plan §4.6), so the suite starts clean.
    """
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    engine = create_sync_engine(url, pool_size=1)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "DROP TABLE IF EXISTS karr_environments, karr_agent_registrations, "
                    "karr_projects, karr_agents, schema_migrations, alembic_version CASCADE"
                )
            )
    finally:
        engine.dispose()
    return url


@pytest.fixture
def live_config(database_url: str) -> KarrConfig:
    return KarrConfig(
        component="karr",
        database_url=SecretStr(database_url),
        admin_token=SecretStr(ADMIN),
        secret_key=SecretStr(Fernet.generate_key().decode()),
        trusted_proxies=["10.0.0.0/8"],
        public_url="https://karr.test",
    )


@pytest.fixture
def clean_tables(database_url: str) -> Iterator[None]:
    engine = create_sync_engine(database_url, pool_size=1)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "DO $$ BEGIN IF to_regclass('karr_environments') IS NOT NULL THEN "
                    "TRUNCATE karr_environments, karr_projects, karr_agents, karr_agent_registrations CASCADE; "
                    "END IF; END $$;"
                )
            )
        yield
    finally:
        engine.dispose()


@pytest.fixture
def api(live_config: KarrConfig, clean_tables: None) -> Iterator[TestClient]:
    """The full app with its lifespan (migrations, registry) against the live DB."""
    app = create_app(live_config)
    with TestClient(
        app, base_url="http://karr.test", client=("10.0.0.1", 50000)
    ) as client:
        client.headers["Authorization"] = f"Bearer {ADMIN}"
        yield client
