"""FastAPI application factory and the ``serve`` lifespan (plan §5.2)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from flag_commons.database import connect, run_migrations_async
from flag_commons.health import DatabaseChecker, Registry
from flag_commons.health.fastapi import health_router
from flag_commons.secrets import provider_from_env

from karr import DIST_NAME, __version__
from karr.api.errors import install_error_handlers
from karr.api.middleware import install_middleware
from karr.api.routers import auth, metrics
from karr.config import KarrConfig
from karr.db import MIGRATIONS_DIR
from karr.db.session import make_session_factory
from karr.security import TokenCipher

STATIC_DIR = Path(__file__).parent / "web" / "static"

_log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Bootstrap in the Go order: secrets, config, logging, db, migrations, health."""
    cfg: KarrConfig | None = getattr(app.state, "config", None)
    if cfg is None:
        cfg = KarrConfig.load(provider_from_env())
        app.state.config = cfg
        cfg.setup_logging(dist_name=DIST_NAME)
    _log.info("starting karr: version=%s addr=%s", __version__, cfg.listen_addr)

    url = cfg.database_url.get_secret_value()
    engine = await connect(url)
    await run_migrations_async(MIGRATIONS_DIR, url)
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.cipher = TokenCipher(cfg.secret_key.get_secret_value())

    health = Registry(dist_name=DIST_NAME)
    health.register(DatabaseChecker(engine))
    app.state.health = health
    app.include_router(health_router(health, DIST_NAME))
    try:
        yield
    finally:
        await engine.dispose()
        _log.info("karr stopped")


def create_app(
    config: KarrConfig | None = None, *, bootstrap: bool = True, spa: bool = True
) -> FastAPI:
    """Build the app.

    ``bootstrap=False`` skips the database lifespan and ``spa=False`` skips the
    catch-all static route; both exist for tests that add their own routes.
    """
    app = FastAPI(
        title="KARR API",
        description="Control plane for AI dev environments on BONNIE GPU hosts",
        version=__version__,
        lifespan=lifespan if bootstrap else None,
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/v1/openapi.json",
    )
    if config is not None:
        app.state.config = config
    cors = list(config.cors_origins) if config else []
    hsts = bool(config.enable_hsts) if config else False

    install_error_handlers(app)
    install_middleware(app, cors_origins=cors, enable_hsts=hsts)
    app.include_router(metrics.router)
    app.include_router(auth.router)
    if not bootstrap:
        health = Registry(dist_name=DIST_NAME)
        app.state.health = health
        app.include_router(health_router(health, DIST_NAME))
    if spa:
        mount_spa(app)
    return app


def mount_spa(app: FastAPI, static_dir: Path = STATIC_DIR) -> None:
    """Serve the built SPA with an index.html fallback, guarded against traversal."""
    index = static_dir / "index.html"
    if (static_dir / "assets").is_dir():
        app.mount(
            "/assets", StaticFiles(directory=static_dir / "assets"), name="assets"
        )

    @app.get("/{path:path}", include_in_schema=False, response_model=None)
    async def spa_fallback(request: Request, path: str) -> Response:
        if path.startswith("api/") or path in ("health", "ready", "metrics"):
            return JSONResponse({"error": "not found"}, status_code=404)
        if not index.is_file():
            return JSONResponse({"error": "frontend not built"}, status_code=404)
        root = static_dir.resolve()
        candidate = (static_dir / path).resolve()
        if candidate.is_relative_to(root) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)
