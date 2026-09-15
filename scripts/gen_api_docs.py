#!/usr/bin/env python3
"""Render docs/api.md from KARR's OpenAPI schema.

Usage: ``poetry run python scripts/gen_api_docs.py > docs/api.md`` (``make api-docs``).
The schema comes from ``create_app`` directly, so the document always matches
the code; hand-written notes live in the PREAMBLE and NOTES tables below.
"""

from __future__ import annotations

import json
import sys
from typing import Any

PREAMBLE = """# KARR API Reference

Generated from the OpenAPI schema (`karr openapi`); do not edit by hand, run
`make api-docs`. Base URL in kitt-stack: `https://karr.internal.kirby.network`.

**Authentication.** Routes marked *admin* need `Authorization: Bearer <KARR_ADMIN_TOKEN>`.
`/health`, `/ready`, `/metrics`, `/api/v1/install.sh` and `/api/v1/agents/register`
are open; the last two are gated by a one-time registration token instead.

**Errors.** Every error body is `{"error": "<message>"}`: 400 for a missing or
malformed JSON body, 422 for a body that fails validation (the message names the
field), 401 without a valid bearer, 404 for an unknown id, 409 for a state
conflict, 413 past the 1 MiB body limit, 429 when a rate limit trips (with
`Retry-After`), 502 when BONNIE refuses an operation, 503 when provisioning is
not configured.

**Omitted fields.** Optional response fields (`project_id`, `container_id`,
`status_message`, `last_seen_at`, `claimed_at`, `agent_id`, empty `env`/`mounts`/
`command`) are absent rather than `null`, as in the Go service.
"""

# Per-route notes the schema cannot express (status codes raised in services).
NOTES: dict[tuple[str, str], str] = {
    ("get", "/health"): "Liveness only; never touches a dependency.",
    (
        "get",
        "/ready",
    ): "Runs every registered check. `database` is critical; `bonnie-agents` and `reconciler` are informational, so an empty control plane is still ready. 503 when a critical check fails.",
    (
        "get",
        "/metrics",
    ): "Prometheus text: `karr_http_requests_total`, `karr_http_request_duration_seconds`, `karr_build_info`, plus the `process_*`, `python_*` collectors.",
    (
        "get",
        "/api/v1/auth/check",
    ): "204 with a valid token, 401 otherwise. The SPA's sign-in form calls it, so it is rate limited per client (429).",
    (
        "post",
        "/api/v1/agents/provision",
    ): "Creates a pending registration and returns the one-shot install command; 503 until `KARR_PUBLIC_URL` is set. Rate limited per client.",
    (
        "delete",
        "/api/v1/agents/registrations/{registration_id}",
    ): "404 for an unknown id.",
    (
        "get",
        "/api/v1/install.sh",
    ): "Query `token=<registration token>`. Serves the BONNIE installer only for a pending, unexpired registration (404 otherwise). Plain-http server URLs need `KARR_ALLOW_INSECURE_INSTALL`.",
    (
        "post",
        "/api/v1/agents/register",
    ): "Called by the installer with the registration token; claims it and creates the agent in one transaction. 401 for an unknown or expired token, 409 for a name clash. Rate limited per client; `X-Forwarded-For` is honoured only from `KARR_TRUSTED_PROXIES`.",
    (
        "post",
        "/api/v1/agents",
    ): "`url` must be an http(s) URL without credentials; 409 when the name exists.",
    (
        "delete",
        "/api/v1/agents/{agent_id}",
    ): "409 while environments reference the agent unless `force=true`, which deletes them from KARR (their containers are left on the host).",
    (
        "get",
        "/api/v1/agents/{agent_id}/status",
    ): "`system` and `gpu` are present only while the agent is online and BONNIE answered; `gpu.gpus` can be `null` on hosts without a GPU.",
    ("post", "/api/v1/projects"): "409 when the name exists.",
    (
        "put",
        "/api/v1/projects/{project_id}",
    ): "A `null` or absent field is left unchanged.",
    (
        "delete",
        "/api/v1/projects/{project_id}",
    ): "Environments keep running and lose their `project_id`.",
    (
        "post",
        "/api/v1/environments",
    ): "400 for an unknown `agent_id` or `project_id`; 409 when the name exists on that agent. The row is created first, then the container; a BONNIE failure leaves the row in `error` with `status_message` and answers 502.",
    (
        "post",
        "/api/v1/environments/{env_id}/start",
    ): "409 unless the environment is `stopped`.",
    (
        "post",
        "/api/v1/environments/{env_id}/stop",
    ): "409 unless the environment is `running`.",
    (
        "delete",
        "/api/v1/environments/{env_id}",
    ): "Removes the container, then the row. 409 while a create is in flight; a container BONNIE no longer knows about is dropped once the reconciler has marked it missing.",
    (
        "get",
        "/api/v1/environments/{env_id}/logs",
    ): "`text/event-stream`. Each log line is one `data:` frame with backslash, CR and LF escaped as `\\\\`, `\\r`, `\\n`; `: keepalive` every 15 s; `event: end` when the container's stream closes (or after the 4 h stream limit), `event: error` with a message on failure. 409 when the environment has no container, 429 past 8 concurrent streams per agent.",
}

SECTION_ORDER = [
    "health",
    "metrics",
    "auth",
    "registrations",
    "install",
    "agents",
    "projects",
    "environments",
]
SECTION_TITLES = {
    "health": "Health",
    "metrics": "Metrics",
    "auth": "Auth",
    "registrations": "Agent provisioning",
    "install": "Agent installation",
    "agents": "Agents",
    "projects": "Projects",
    "environments": "Environments",
}


def deref(schema: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        schema = spec["components"]["schemas"][name]
    return schema


def type_name(schema: dict[str, Any], spec: dict[str, Any]) -> str:
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    if "anyOf" in schema:
        parts = [type_name(s, spec) for s in schema["anyOf"] if s.get("type") != "null"]
        nullable = len(parts) < len(schema["anyOf"])
        joined = " or ".join(parts)  # never "|": it would split the Markdown table
        return f"{joined}, nullable" if nullable else joined
    t = schema.get("type", "object")
    if t == "array":
        return f"{type_name(schema.get('items', {}), spec)}[]"
    if schema.get("format"):
        return f"{t} ({schema['format']})"
    return str(t)


def field_table(schema: dict[str, Any], spec: dict[str, Any]) -> list[str]:
    schema = deref(schema, spec)
    props = schema.get("properties", {})
    if not props:
        return []
    required = set(schema.get("required", []))
    lines = ["| Field | Type | Required | Notes |", "|---|---|---|---|"]
    for name, prop in props.items():
        notes = []
        if "default" in prop and prop["default"] not in ("", [], None):
            notes.append(f"default `{json.dumps(prop['default'])}`")
        if prop.get("maxLength"):
            notes.append(f"max {prop['maxLength']} chars")
        if prop.get("description"):
            notes.append(prop["description"])
        lines.append(
            f"| `{name}` | {type_name(prop, spec)} | {'yes' if name in required else 'no'} | {'; '.join(notes)} |"
        )
    return lines


def render(spec: dict[str, Any]) -> str:
    out = [PREAMBLE]
    by_tag: dict[str, list[tuple[str, str, dict[str, Any]]]] = {}
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            tag = (op.get("tags") or ["other"])[0]
            by_tag.setdefault(tag, []).append((method, path, op))
    seen_schemas: list[str] = []
    for tag in SECTION_ORDER + [t for t in by_tag if t not in SECTION_ORDER]:
        if tag not in by_tag:
            continue
        out.append(f"\n## {SECTION_TITLES.get(tag, tag.title())}\n")
        for method, path, op in by_tag[tag]:
            auth = " *(admin)*" if op.get("security") else ""
            out.append(f"### {method.upper()} {path}{auth}\n")
            if op.get("description"):
                out.append(op["description"].strip() + "\n")
            note = NOTES.get((method, path))
            if note:
                out.append(note + "\n")
            params = [p for p in op.get("parameters", []) if p["in"] != "path"]
            if params:
                out.append("| Query | Type | Required | Notes |\n|---|---|---|---|")
                for p in params:
                    out.append(
                        f"| `{p['name']}` | {type_name(p.get('schema', {}), spec)} | {'yes' if p.get('required') else 'no'} | {p.get('description', '')} |"
                    )
                out.append("")
            body = (
                op.get("requestBody", {})
                .get("content", {})
                .get("application/json", {})
                .get("schema")
            )
            if body:
                out.append(f"**Request body** — `{type_name(body, spec)}`\n")
                rows = field_table(body, spec)
                if rows:
                    out.extend(rows)
                    out.append("")
            for code, resp in op.get("responses", {}).items():
                if (
                    code == "422"
                    and "requestBody" not in op
                    and not op.get("parameters")
                ):
                    continue
                if code == "422":
                    continue  # covered by the error envelope note above
                content = resp.get("content", {})
                schema = content.get("application/json", {}).get("schema")
                if schema:
                    name = type_name(schema, spec)
                    out.append(f"**Response {code}** — `{name}`")
                    base = deref(
                        schema.get("items", schema)
                        if schema.get("type") == "array"
                        else schema,
                        spec,
                    )
                    ref = (
                        schema.get("items", schema)
                        if schema.get("type") == "array"
                        else schema
                    ).get("$ref")
                    if ref and ref.rsplit("/", 1)[-1] not in seen_schemas:
                        seen_schemas.append(ref.rsplit("/", 1)[-1])
                        rows = field_table(base, spec)
                        if rows:
                            out.append("")
                            out.extend(rows)
                    out.append("")
                elif "text/event-stream" in content:
                    out.append(f"**Response {code}** — `text/event-stream`\n")
                elif content:
                    out.append(f"**Response {code}** — `{', '.join(content)}`\n")
                else:
                    out.append(f"**Response {code}** — no body\n")
    return "\n".join(out).rstrip() + "\n"


def load_spec() -> dict[str, Any]:
    from cryptography.fernet import Fernet
    from pydantic import SecretStr

    from karr.app import create_app
    from karr.config import KarrConfig

    cfg = KarrConfig(
        component="karr",
        admin_token=SecretStr("schema-only-placeholder-token"),
        secret_key=SecretStr(Fernet.generate_key().decode()),
    )
    return create_app(cfg, bootstrap=False, spa=False).openapi()


if __name__ == "__main__":
    sys.stdout.write(render(load_spec()))
