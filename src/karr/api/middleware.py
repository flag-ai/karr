"""Security headers, request logging + metrics, body limit and CORS.

Everything here is pure ASGI so it works uniformly for responses produced by
routers, by other middleware (413, CORS preflight) and by Starlette's
outermost error handler. Order, outermost first:
security headers → request log/metrics → CORS → body limit → app.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from fastapi import FastAPI
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
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
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

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                existing = {k.lower() for k, _ in message.get("headers", [])}
                extra = [(k, v) for k, v in self.headers if k not in existing]
                message["headers"] = list(message.get("headers", [])) + extra
            await send(message)

        await self.app(scope, receive, send_with_headers)


class RequestLogMiddleware:
    """One log line and two Prometheus series per request, 413s and 500s included."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start = time.perf_counter()
        status = 500

        async def send_and_record(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, send_and_record)
        finally:
            elapsed = time.perf_counter() - start
            route = scope.get("route")
            template = getattr(route, "path", None)
            route_label = template if isinstance(template, str) else "unmatched"
            method = scope.get("method", "")
            REQUESTS.labels(method, route_label, str(status)).inc()
            LATENCY.labels(method, route_label).observe(elapsed)
            client = scope.get("client")
            _log.info(
                "http",
                extra={
                    "method": method,
                    "path": scope.get("path", ""),
                    "status": status,
                    "duration_ms": round(elapsed * 1000, 1),
                    "remote": client[0] if client else "",
                },
            )


def _json_messages(status: int, payload: dict[str, str]) -> tuple[Message, Message]:
    body = json.dumps(payload).encode()
    start: Message = {
        "type": "http.response.start",
        "status": status,
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ],
    }
    return start, {"type": "http.response.body", "body": body}


class BodyLimitMiddleware:
    """413 on a declared or streamed body over ``max_bytes``, before it is buffered.

    Once the streamed total exceeds the cap the wrapped ``receive`` hands the
    app a disconnect instead of more body, so nothing downstream ever buffers
    past the limit. Whatever the app then does (raise, or return), the
    middleware answers 413 unless a response already started. Exceptions are
    never raised *through* the app: Starlette's base middleware would wrap
    them in an ExceptionGroup and the 413 would turn into a 500.
    """

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
        over = False
        response_started = False

        async def counting_receive() -> Message:
            nonlocal total, over
            if over:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > self.max_bytes:
                    over = True
                    return {"type": "http.disconnect"}
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if over and not response_started:
                # The app is answering its own way (e.g. a 400 for a cut-off
                # body); the 413 below replaces it.
                return
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, tracking_send)
        except BaseException:
            if not over:
                raise
        if over:
            if response_started:
                _log.warning(
                    "request body exceeded %d bytes after the response started: path=%s",
                    self.max_bytes,
                    scope.get("path", ""),
                )
            else:
                await self._reject(send)

    @staticmethod
    async def _reject(send: Send) -> None:
        for message in _json_messages(413, {"error": "request body too large"}):
            await send(message)


def _content_length(scope: Scope) -> int | None:
    for key, value in scope.get("headers", []):
        if key.lower() == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


def cors_headers_for(origin: str | None, allowed: list[str]) -> dict[str, str]:
    """Headers a handler outside CORSMiddleware (the 500 handler) must add itself."""
    if origin and origin in allowed:
        return {"access-control-allow-origin": origin, "vary": "Origin"}
    return {}


def install_middleware(
    app: FastAPI, *, cors_origins: list[str], enable_hsts: bool
) -> None:
    """Register every middleware; ``add_middleware`` order makes the last one outermost."""
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
    app.add_middleware(RequestLogMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, enable_hsts=enable_hsts)
