"""FastAPI application factory and the ``serve`` lifespan (plan §5.2)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from flag_commons.bonnie import AgentRegistry, BonnieAgentsChecker
from flag_commons.database import connect, run_migrations_async
from flag_commons.health import DatabaseChecker, Registry
from flag_commons.health.fastapi import health_router

from karr import DIST_NAME, __version__
from karr.api.errors import install_error_handlers
from karr.api.middleware import install_middleware
from karr.api.ratelimit import RateLimiter, rate_limited
from karr.api.routers import (
    agents,
    auth,
    environments,
    metrics,
    projects,
    registrations,
)
from karr.bonnie_store import KarrRegistryStore
from karr.config import KarrConfig
from karr.db import MIGRATIONS_DIR
from karr.db.session import make_session_factory
from karr.security import TokenCipher
from karr.services.reconcile import Reconciler
from karr.services.seed import ensure_default_agent

STATIC_DIR = Path(__file__).parent / "web" / "static"

_log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Bootstrap in the Go order: config, engine, migrations, health checks."""
    cfg: KarrConfig = app.state.config
    _log.info("starting karr: version=%s addr=%s", __version__, cfg.listen_addr)

    url = cfg.database_url.get_secret_value()
    engine = await connect(url)
    registry: AgentRegistry | None = None
    reconciler: Reconciler | None = None
    starter: asyncio.Task[None] | None = None
    try:
        await run_migrations_async(MIGRATIONS_DIR, url)
        sessions = make_session_factory(engine)
        cipher = TokenCipher(cfg.secret_key.get_secret_value())
        app.state.engine = engine
        app.state.session_factory = sessions
        app.state.cipher = cipher

        if cfg.default_agent_url:
            try:
                await ensure_default_agent(
                    sessions,
                    cipher,
                    cfg.default_agent_url,
                    cfg.default_agent_token.get_secret_value(),
                )
            except Exception as exc:  # noqa: BLE001 - seeding is best effort, like Go
                _log.warning("failed to register default agent: %s", exc)

        registry = AgentRegistry(KarrRegistryStore(sessions, cipher))
        app.state.registry = registry
        app.state.health.register(DatabaseChecker(engine))
        app.state.health.register(BonnieAgentsChecker(registry), critical=False)
        # The first poll probes every agent with retries; run it in the
        # background so an unreachable host cannot stall startup and /health.
        starter = asyncio.create_task(registry.start(), name="bonnie-registry-start")
        starter.add_done_callback(_log_task_failure)
        reconciler = Reconciler(sessions, registry)
        reconciler.start()
        app.state.reconciler = reconciler
        yield
    finally:
        if reconciler is not None:
            await reconciler.stop()
        if registry is not None:
            if starter is not None and not starter.done():
                starter.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await starter
            await registry.stop()
        await engine.dispose()
        _log.info("karr stopped")


def _log_task_failure(task: asyncio.Task[None]) -> None:
    if not task.cancelled() and task.exception() is not None:
        _log.error(
            "background task %s failed", task.get_name(), exc_info=task.exception()
        )


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
    for name, capacity, refill in (
        auth.AUTH_LIMIT,
        registrations.PROVISION_LIMIT,
        registrations.REGISTER_LIMIT,
    ):
        setattr(app.state, name, RateLimiter(capacity, refill))
    if config.allow_insecure_install:
        _log.warning(
            "KARR_ALLOW_INSECURE_INSTALL is on: install scripts may phone home over plain http"
        )
    if not config.public_url:
        _log.warning(
            "KARR_PUBLIC_URL is not set: provisioning will answer 503 until it is"
        )
    if not config.trusted_proxies:
        _log.warning(
            "KARR_TRUSTED_PROXIES is empty: rate limits key on the direct peer address"
        )
    if not bootstrap:
        # Tests provide their own engine/session factory; give them a registry
        # and cipher so the routers can run.
        app.state.registry = AgentRegistry(None, poll_interval=0)
        app.state.cipher = TokenCipher(config.secret_key.get_secret_value())

    install_error_handlers(app)
    install_middleware(
        app, cors_origins=list(config.cors_origins), enable_hsts=config.enable_hsts
    )
    app.include_router(health_router(app.state.health, DIST_NAME, redact_errors=True))
    app.include_router(metrics.router)
    app.include_router(auth.router)
    # Static /agents/... routes must precede /agents/{id}: registrations first.
    app.include_router(registrations.admin_router)
    app.include_router(
        registrations.public_router(app),
        prefix="/api/v1",
        dependencies=[Depends(rate_limited(registrations.REGISTER_LIMIT[0]))],  # K-D23
    )
    app.include_router(agents.router)
    app.include_router(projects.router)
    app.include_router(environments.router)
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

    @app.api_route(
        "/api/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
        include_in_schema=False,
        response_model=None,
    )
    async def unknown_api_route(path: str) -> Response:
        # Unknown API paths are 404 for every method, as in Go; without this the
        # GET-only catch-all below would answer 405 to POST/PUT/DELETE.
        return JSONResponse({"error": "not found"}, status_code=404)

    @app.api_route(
        "/{path:path}",
        methods=["GET", "HEAD"],
        include_in_schema=False,
        response_model=None,
    )
    async def spa_fallback(request: Request, path: str) -> Response:
        if not index.is_file():
            return JSONResponse({"error": "frontend not built"}, status_code=404)
        root = static_dir.resolve()
        try:
            candidate = (static_dir / path).resolve()
            if candidate.is_relative_to(root) and candidate.is_file():
                return FileResponse(candidate)
        except (OSError, ValueError):  # null bytes, over-long names
            pass
        return FileResponse(index)
