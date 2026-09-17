"""Admin authentication, token hashing and encryption at rest."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Annotated

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

REGISTRATION_TOKEN_BYTES = 32  # 64 hex characters, shown once

_bearer = HTTPBearer(auto_error=False)


def token_matches(presented: str | None, expected: str) -> bool:
    """Constant-time comparison; an empty expected token never matches."""
    if not presented or not expected:
        return False
    return hmac.compare_digest(presented.encode(), expected.encode())


async def require_admin(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ] = None,
) -> None:
    """FastAPI dependency: the request must carry the admin bearer token (K-D1)."""
    expected = request.app.state.config.admin_token.get_secret_value()
    presented = credentials.credentials if credentials else None
    if not token_matches(presented, expected):
        raise HTTPException(status_code=401, detail="unauthorized")


def generate_registration_token() -> str:
    return secrets.token_hex(REGISTRATION_TOKEN_BYTES)


def hash_registration_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class TokenCipher:
    """Fernet encryption for BONNIE agent tokens at rest (K-D12).

    The token must stay recoverable because KARR presents it to BONNIE, so it
    is encrypted rather than hashed.
    """

    def __init__(self, key: str) -> None:
        self._fernet = Fernet(key.encode())

    def encrypt(self, plaintext: str) -> str:
        if not plaintext:
            return ""
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        if not ciphertext:
            return ""
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken as exc:
            raise ValueError(
                "stored agent token cannot be decrypted with KARR_SECRET_KEY"
            ) from exc
