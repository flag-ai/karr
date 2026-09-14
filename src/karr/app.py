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
    """Bootstrap in the Go order: config, engine, migrations, health checks."""
    cfg: KarrConfig = app.state.config
    _log.info("starting karr: version=%s addr=%s", __version__, cfg.listen_addr)

    url = cfg.database_url.get_secret_value()
    engine = await connect(url)
    try:
        await run_migrations_async(MIGRATIONS_DIR, url)
        app.state.engine = engine
        app.state.session_factory = make_session_factory(engine)
        app.state.cipher = TokenCipher(cfg.secret_key.get_secret_value())
        app.state.health.register(DatabaseChecker(engine))
        yield
    finally:
        await engine.dispose()
        _log.info("karr stopped")


def create_app(
    config: KarrConfig, *, bootstrap: bool = True, spa: bool = True
) -> FastAPI:
    """Build the app.

    ``bootstrap=False`` skips the database lifespan and ``spa=False`` skips the
    catch-all static route; both exist for tests that add their own routes.
    Every router is registered here, before the SPA catch-all, because
    Starlette matches routes in registration order.
    """
    app = FastAPI(
        title="KARR API",
        description="Control plane for AI dev environments on BONNIE GPU hosts",
        version=__version__,
        lifespan=lifespan if bootstrap else None,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,  # `karr openapi` prints the schema for docs/api.md
    )
    app.state.config = config
    app.state.health = Registry(dist_name=DIST_NAME)

    install_error_handlers(app)
    install_middleware(
        app, cors_origins=list(config.cors_origins), enable_hsts=config.enable_hsts
    )
    app.include_router(health_router(app.state.health, DIST_NAME, redact_errors=True))
    app.include_router(metrics.router)
    app.include_router(auth.router)
    if spa:
        mount_spa(app)
    return app


def mount_spa(app: FastAPI, static_dir: Path = STATIC_DIR) -> None:
    """Serve the built SPA with an index.html fallback, guarded against traversal.

    Must be called last: it registers the catch-all route.
    """
    index = static_dir / "index.html"
    if (static_dir / "assets").is_dir():
        app.mount(
            "/assets", StaticFiles(directory=static_dir / "assets"), name="assets"
        )

    @app.get("/{path:path}", include_in_schema=False, response_model=None)
    async def spa_fallback(request: Request, path: str) -> Response:
        if path.startswith("api/"):
            return JSONResponse({"error": "not found"}, status_code=404)
        if not index.is_file():
            return JSONResponse({"error": "frontend not built"}, status_code=404)
        root = static_dir.resolve()
        candidate = (static_dir / path).resolve()
        if candidate.is_relative_to(root) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)
