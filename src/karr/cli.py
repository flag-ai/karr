"""``karr serve``, ``karr migrate up`` and ``karr version``."""

from __future__ import annotations

import sys

import click
from flag_commons import version as flag_version
from flag_commons.config import ConfigError
from flag_commons.database import run_migrations
from flag_commons.logging import uvicorn_log_config
from flag_commons.secrets import provider_from_env

from karr import DIST_NAME, __version__
from karr.config import KarrConfig
from karr.db import MIGRATIONS_DIR


def _load_config() -> KarrConfig:
    try:
        cfg = KarrConfig.load(provider_from_env())
    except ConfigError as exc:
        raise click.ClickException(str(exc)) from exc
    cfg.setup_logging(dist_name=DIST_NAME)
    return cfg


@click.group()
@click.version_option(__version__, prog_name="karr")
def cli() -> None:
    """KARR — Kirizan's AI Refinement Runtime."""


@cli.command()
@click.option("--host", default=None, help="Bind address (default: from LISTEN_ADDR).")
@click.option(
    "--port", default=None, type=int, help="Bind port (default: from LISTEN_ADDR)."
)
def serve(host: str | None, port: int | None) -> None:
    """Start the KARR server."""
    import uvicorn

    from karr.app import create_app

    cfg = _load_config()
    bind_host, bind_port = cfg.bind_address()
    uvicorn.run(
        create_app(cfg),
        host=host or bind_host,
        port=port or bind_port,
        log_config=uvicorn_log_config(
            DIST_NAME, level=cfg.log_level, fmt=cfg.log_format
        ),
        timeout_graceful_shutdown=10,
    )


@cli.group()
def migrate() -> None:
    """Database migrations."""


@migrate.command()
def up() -> None:
    """Apply all pending migrations."""
    cfg = _load_config()
    run_migrations(MIGRATIONS_DIR, cfg.database_url.get_secret_value())
    click.echo("migrations complete")


@cli.command()
def version() -> None:
    """Print the version, commit and build date."""
    click.echo(flag_version.info(DIST_NAME))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(cli())
