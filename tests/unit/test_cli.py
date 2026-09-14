from __future__ import annotations

from click.testing import CliRunner

from karr import __version__
from karr.cli import cli


def test_version() -> None:
    result = CliRunner().invoke(cli, ["version"])
    assert result.exit_code == 0
    assert result.output.startswith(f"{__version__} (commit: ")


def test_missing_config_is_a_clean_error(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    for k in ("DATABASE_URL", "KARR_ADMIN_TOKEN", "KARR_SECRET_KEY"):
        monkeypatch.delenv(k, raising=False)
    result = CliRunner().invoke(cli, ["migrate", "up"])
    assert result.exit_code != 0
    assert "DATABASE_URL" in result.output
