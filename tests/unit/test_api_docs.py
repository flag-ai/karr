from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "gen_api_docs.py"


def _load() -> object:
    spec = importlib.util.spec_from_file_location("gen_api_docs", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generated_api_docs_cover_every_route() -> None:
    gen = _load()
    spec = gen.load_spec()  # type: ignore[attr-defined]
    text = gen.render(spec)  # type: ignore[attr-defined]
    for path, ops in spec["paths"].items():
        for method in ops:
            assert f"### {method.upper()} {path}" in text, (method, path)
    assert "**Request body** — `EnvironmentCreate`" in text
    assert "| `agent_id` | string (uuid) | yes |" in text
    assert "text/event-stream" in text
    # every hand-written note points at a route that exists
    for method, path in gen.NOTES:  # type: ignore[attr-defined]
        assert method in spec["paths"].get(path, {}), (method, path)


def test_committed_api_docs_are_current() -> None:
    gen = _load()
    committed = (SCRIPT.parents[1] / "docs" / "api.md").read_text(encoding="utf-8")
    assert committed == gen.render(gen.load_spec()), (  # type: ignore[attr-defined]
        "docs/api.md is stale: run `make api-docs` and commit the result"
    )
