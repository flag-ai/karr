"""KARR — Kirizan's AI Refinement Runtime."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _dist_version

DIST_NAME = "karr"

try:
    __version__ = _dist_version(DIST_NAME)
except PackageNotFoundError:  # pragma: no cover
    __version__ = "dev"

__all__ = ["DIST_NAME", "__version__"]
