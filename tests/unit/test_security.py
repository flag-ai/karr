from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from karr.security import (
    TokenCipher,
    generate_registration_token,
    hash_registration_token,
    token_matches,
)


def test_token_matches() -> None:
    assert token_matches("abc", "abc")
    assert not token_matches("abd", "abc")
    assert not token_matches(None, "abc")
    assert not token_matches("", "")
    assert not token_matches("x", "")


def test_registration_tokens() -> None:
    tok = generate_registration_token()
    assert len(tok) == 64 and int(tok, 16) >= 0
    assert generate_registration_token() != tok
    assert hash_registration_token(tok) == hash_registration_token(tok)
    assert len(hash_registration_token(tok)) == 64


def test_token_cipher_round_trip() -> None:
    cipher = TokenCipher(Fernet.generate_key().decode())
    blob = cipher.encrypt("bonnie-secret")
    assert blob != "bonnie-secret" and "bonnie-secret" not in blob
    assert cipher.decrypt(blob) == "bonnie-secret"
    assert cipher.encrypt("") == "" and cipher.decrypt("") == ""
    other = TokenCipher(Fernet.generate_key().decode())
    with pytest.raises(ValueError, match="KARR_SECRET_KEY"):
        other.decrypt(blob)


def test_auth_check(client: TestClient, auth: dict[str, str]) -> None:
    # K-D1: every /api/v1 route is behind the admin bearer token.
    assert client.get("/api/v1/auth/check").status_code == 401
    assert client.get("/api/v1/auth/check").json() == {"error": "unauthorized"}
    assert (
        client.get(
            "/api/v1/auth/check", headers={"Authorization": "Bearer nope"}
        ).status_code
        == 401
    )
    assert (
        client.get(
            "/api/v1/auth/check", headers={"Authorization": "Basic abc"}
        ).status_code
        == 401
    )
    assert client.get("/api/v1/auth/check", headers=auth).status_code == 204
