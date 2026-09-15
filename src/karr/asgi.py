"""ASGI entry point for ``uvicorn karr.asgi:app`` (development reload, WSGI hosts).

``karr serve`` remains the production entry point: it also wires uvicorn's log
config and proxy-header trust from the configuration. This module only builds
the app from the environment so a reloader can import it.
"""

from __future__ import annotations

from flag_commons.secrets import provider_from_env

from karr import DIST_NAME
from karr.app import create_app
from karr.config import KarrConfig

config = KarrConfig.load(provider_from_env())
config.setup_logging(dist_name=DIST_NAME)
app = create_app(config)
