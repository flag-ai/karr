"""ASGI entry point for ``uvicorn karr.asgi:app`` (development reload).

``karr serve`` remains the production entry point: it also wires uvicorn's log
config. Proxy-header trust is applied here too, so rate limits key on the real
client behind a proxy listed in ``KARR_TRUSTED_PROXIES`` exactly as under
``karr serve``; run uvicorn without ``--proxy-headers`` (it would trust every
peer).
"""

from __future__ import annotations

from typing import Any, cast

from flag_commons.secrets import provider_from_env
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from karr import DIST_NAME
from karr.app import create_app
from karr.config import KarrConfig

config = KarrConfig.load(provider_from_env())
config.setup_logging(dist_name=DIST_NAME)
app = ProxyHeadersMiddleware(
    cast(
        Any, create_app(config)
    ),  # FastAPI is ASGI3; uvicorn's stub wants the typed alias
    trusted_hosts=list(config.trusted_proxies)
    if config.trusted_proxies
    else "127.0.0.1",
)
