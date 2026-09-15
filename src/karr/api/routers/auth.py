"""``GET /api/v1/auth/check``: 204 with a valid admin token, 401 otherwise."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from karr.api.ratelimit import rate_limited
from karr.security import require_admin

# The SPA's sign-in form posts guesses here, so the endpoint must not be a
# full-speed token oracle: 20 checks per client, then one every 5 s.
AUTH_LIMIT = ("auth_limiter", 20, 0.2)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.get(
    "/check",
    status_code=204,
    dependencies=[Depends(rate_limited(AUTH_LIMIT[0])), Depends(require_admin)],
)
async def check() -> Response:
    return Response(status_code=204)
