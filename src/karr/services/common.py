"""Helpers shared by the services."""

from __future__ import annotations

import uuid
from urllib.parse import urlsplit

from fastapi import Request
from flag_commons.bonnie import AgentRegistry
from sqlalchemy.exc import IntegrityError

from karr.api.errors import ApiError
from karr.security import TokenCipher


def parse_uuid(value: str, what: str) -> uuid.UUID:
    """``400 {"error": "invalid <what> id"}`` for a malformed id, like Go."""
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ApiError(400, f"invalid {what} id") from exc


def validate_agent_url(url: str) -> str:
    """Only http(s) with a host (K-D13). Private IPs stay allowed by design.

    Trailing slashes are dropped so the same host is stored one way (Go kept
    the URL verbatim).
    """
    url = url.strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ApiError(422, "url must be an http or https URL with a host")
    if parts.username or parts.password:
        raise ApiError(422, "url must not contain credentials")
    try:
        port = parts.port  # raises for "h:443:7777" and non-numeric ports
    except ValueError as exc:
        raise ApiError(422, "url has an invalid port") from exc
    if port == 0:
        raise ApiError(422, "url has an invalid port")
    return url.rstrip("/")


def is_unique_violation(exc: IntegrityError) -> bool:
    return getattr(getattr(exc, "orig", None), "sqlstate", None) == "23505"


def registry_of(request: Request) -> AgentRegistry:
    registry: AgentRegistry = request.app.state.registry
    return registry


def cipher_of(request: Request) -> TokenCipher:
    cipher: TokenCipher = request.app.state.cipher
    return cipher
