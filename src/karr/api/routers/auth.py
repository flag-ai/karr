"""``GET /api/v1/auth/check``: 204 with a valid admin token, 401 otherwise."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from karr.security import require_admin

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.get("/check", status_code=204, dependencies=[Depends(require_admin)])
async def check() -> Response:
    return Response(status_code=204)
