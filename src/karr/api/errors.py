"""The ``{"error": "<msg>"}`` envelope every KARR error uses."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

_log = logging.getLogger(__name__)

# Routing-level errors use the same lowercase style as the Go handlers.
_FRAMEWORK_MESSAGES = {404: "not found", 405: "method not allowed"}


class ApiError(Exception):
    """Raise from services and routers to answer with a status and message."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(message)


def error_response(status_code: int, message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status_code)


def _describe_validation(exc: RequestValidationError) -> str:
    """One line naming the offending fields, never echoing their values."""
    parts: list[str] = []
    for err in exc.errors():
        loc = [str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path")]
        field = ".".join(loc) or "body"
        kind = err.get("type", "invalid")
        if kind == "missing":
            parts.append(f"{field} is required")
        elif kind == "extra_forbidden":
            parts.append(f"unknown field {field}")
        elif kind == "json_invalid":
            return "invalid request body"
        else:
            parts.append(f"{field} is invalid")
    return "; ".join(dict.fromkeys(parts)) or "invalid request"


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return error_response(exc.status_code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Malformed JSON is a 400 like Go; a well-formed body failing the
        # schema is 422 (K-D5).
        kinds = {err.get("type") for err in exc.errors()}
        if "json_invalid" in kinds:
            return error_response(400, "invalid request body")
        return error_response(422, _describe_validation(exc))

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else "request failed"
        detail = _FRAMEWORK_MESSAGES.get(exc.status_code, detail)
        headers = dict(exc.headers or {})
        response = error_response(exc.status_code, detail)
        for key, value in headers.items():
            response.headers[key] = value
        return response

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        _log.error(
            "unhandled error: method=%s path=%s",
            request.method,
            request.url.path,
            exc_info=exc,
        )
        response = error_response(500, "internal server error")
        # This handler runs in Starlette's outermost error layer, outside the
        # security-headers middleware, so the headers are applied here too.
        from karr.api.middleware import security_header_pairs

        cfg = getattr(request.app.state, "config", None)
        for key, value in security_header_pairs(bool(cfg and cfg.enable_hsts)):
            response.headers[key.decode()] = value.decode()
        return response
