"""Security headers, body limit, request logging and HTTP metrics.

The pure-ASGI middlewares here run outside FastAPI's exception handling so
they also cover 413s, CORS preflights and 500s. Order (outermost first):
security headers → CORS → body limit → request log/metrics → app.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from fastapi import FastAPI, Request, Response
from prometheus_client import Counter, Histogram
from starlette.middleware.cors import CORSMiddleware

MAX_BODY_BYTES = 1024 * 1024  # 1 MiB (K-D19: 413, not 400)
CORS_MAX_AGE = 600
CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
    "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)

_log = logging.getLogger("karr.http")

REQUESTS = Counter(
    "karr_http_requests_total", "HTTP requests", ["method", "route", "status"]
)
LATENCY = Histogram(
    "karr_http_request_duration_seconds", "HTTP request latency", ["method", "route"]
)

Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


def security_header_pairs(enable_hsts: bool) -> list[tuple[bytes, bytes]]:
    headers = [
        (b"x-frame-options", b"DENY"),
        (b"x-content-type-options", b"nosniff"),
        (b"referrer-policy", b"strict-origin-when-cross-origin"),
        (b"content-security-policy", CSP.encode()),
        (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
    ]
    if enable_hsts:
        headers.append(
            (b"strict-transport-security", b"max-age=31536000; includeSubDomains")
        )
    return headers


class SecurityHeadersMiddleware:
    """Adds the security headers to every response, whatever produced it."""

    def __init__(self, app: ASGIApp, *, enable_hsts: bool = False) -> None:
        self.app = app
        self.headers = security_header_pairs(enable_hsts)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: MutableMapping[str, Any]) -> None:
            if message["type"] == "http.response.start":
                existing = {k.lower() for k, _ in message.get("headers", [])}
                extra = [(k, v) for k, v in self.headers if k not in existing]
                message["headers"] = list(message.get("headers", [])) + extra
            await send(message)

        await self.app(scope, receive, send_with_headers)


class _BodyTooLarge(Exception):
    pass


def _json_message(
    status: int, payload: dict[str, str]
) -> tuple[dict[str, Any], dict[str, Any]]:
    body = json.dumps(payload).encode()
    start = {
        "type": "http.response.start",
        "status": status,
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ],
    }
    return start, {"type": "http.response.body", "body": body}


class BodyLimitMiddleware:
    """413 on a declared or streamed body over ``max_bytes``, before it is buffered."""

    def __init__(self, app: ASGIApp, *, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        declared = _content_length(scope)
        if declared is not None and declared > self.max_bytes:
            await self._reject(send)
            return

        total = 0
        response_started = False

        async def counting_receive() -> MutableMapping[str, Any]:
            nonlocal total
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > self.max_bytes:
                    raise _BodyTooLarge()
            return message

        async def tracking_send(message: MutableMapping[str, Any]) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, tracking_send)
        except _BodyTooLarge:
            if not response_started:
                await self._reject(send)

    @staticmethod
    async def _reject(send: Send) -> None:
        for message in _json_message(413, {"error": "request body too large"}):
            await send(message)


def _content_length(scope: Scope) -> int | None:
    for key, value in scope.get("headers", []):
        if key.lower() == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else "unmatched"


def install_middleware(
    app: FastAPI, *, cors_origins: list[str], enable_hsts: bool
) -> None:
    """Register every middleware; ``add_middleware`` order makes the last one outermost."""

    @app.middleware("http")
    async def request_log_and_metrics(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            elapsed = time.perf_counter() - start
            route = _route_template(request)
            REQUESTS.labels(request.method, route, str(status)).inc()
            LATENCY.labels(request.method, route).observe(elapsed)
            _log.info(
                "http",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": status,
                    "duration_ms": round(elapsed * 1000, 1),
                    "remote": request.client.host if request.client else "",
                },
            )

    app.add_middleware(BodyLimitMiddleware, max_bytes=MAX_BODY_BYTES)
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization"],
            allow_credentials=False,
            max_age=CORS_MAX_AGE,  # K-D14
        )
    app.add_middleware(SecurityHeadersMiddleware, enable_hsts=enable_hsts)
