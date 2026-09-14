"""Security headers, request logging, body limit and HTTP metrics."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram
from starlette.middleware.cors import CORSMiddleware

MAX_BODY_BYTES = 1024 * 1024  # 1 MiB (K-D19: 413, not 400)
CORS_MAX_AGE = 600

_log = logging.getLogger("karr.http")

REQUESTS = Counter(
    "karr_http_requests_total", "HTTP requests", ["method", "route", "status"]
)
LATENCY = Histogram(
    "karr_http_request_duration_seconds", "HTTP request latency", ["method", "route"]
)

Next = Callable[[Request], Awaitable[Response]]


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str):
        return path
    return "unmatched"


def install_middleware(
    app: FastAPI, *, cors_origins: list[str], enable_hsts: bool
) -> None:
    """Order matters: outermost registered last."""

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Next) -> Response:
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "frame-ancestors 'none'",
        )
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        if enable_hsts:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response

    @app.middleware("http")
    async def body_limit(request: Request, call_next: Next) -> Response:
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
            return JSONResponse({"error": "request body too large"}, status_code=413)
        return await call_next(request)

    @app.middleware("http")
    async def request_log_and_metrics(request: Request, call_next: Next) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        route = _route_template(request)
        REQUESTS.labels(request.method, route, str(response.status_code)).inc()
        LATENCY.labels(request.method, route).observe(elapsed)
        _log.info(
            "http",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round(elapsed * 1000, 1),
                "remote": request.client.host if request.client else "",
            },
        )
        return response

    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization"],
            allow_credentials=False,
            max_age=CORS_MAX_AGE,  # K-D14
        )
