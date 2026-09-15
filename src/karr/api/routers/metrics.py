"""``GET /metrics``: Prometheus text, unauthenticated behind Traefik (§0).

``prometheus_client`` registers its process, platform and GC collectors on
import; the HTTP counters live in ``karr.api.middleware``. ``karr_build_info``
carries the running version so the Grafana dashboard can show it.
"""

from __future__ import annotations

from fastapi import APIRouter, Response
from flag_commons import version as flag_version
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, Info, generate_latest

from karr import DIST_NAME

router = APIRouter(tags=["metrics"])

BUILD_INFO = Info("karr_build", "KARR build information")
_info = flag_version.get_info(DIST_NAME)
BUILD_INFO.info({"version": _info.version, "commit": _info.commit, "date": _info.date})


@router.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
