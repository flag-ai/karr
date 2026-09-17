# KARR

**Kirizan's AI Refinement Runtime** — the FLAG control plane that provisions AI
development environments on GPU hosts running [BONNIE](https://github.com/flag-ai/bonnie).
Part of the [FLAG](https://github.com/flag-ai) platform alongside KITT and DEVON,
built on [flag-commons](https://github.com/flag-ai/commons).

> **0.3.0 is a Python rewrite.** The Go service is preserved at tag
> `go-final-0.2.2`. Routes, database schema and SPA are the same; the defects
> fixed on the way are listed by K-D id in [docs/changelog.md](docs/changelog.md).

## What it does

- Registers BONNIE agents (GPU hosts) by hand or through a one-shot install
  command: KARR provisions a registration token, the host runs `install.sh`,
  BONNIE calls back and the agent appears.
- Creates, starts, stops and removes container environments on those agents,
  keeps their status reconciled against the hosts, and relays container logs
  as server-sent events.
- Groups environments into projects.
- Serves a React SPA for all of the above and a JSON API behind an admin bearer
  token; `/health`, `/ready` and `/metrics` stay open for the platform.

Stack: Python 3.10+, FastAPI, SQLAlchemy 2 + psycopg 3, Alembic, PostgreSQL 17,
`flag-commons` (config, secrets, logging, health, database, BONNIE client,
install script), React 19 + Vite 6 frontend, `prometheus_client`.

## Run

```bash
export DATABASE_URL=postgresql://karr:karr@localhost:5432/karr
export KARR_ADMIN_TOKEN=...      # >= 16 chars: python -c 'import secrets; print(secrets.token_urlsafe(32))'
export KARR_SECRET_KEY=...       # Fernet key: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
export KARR_PUBLIC_URL=https://karr.example.com   # embedded in install commands
karr migrate up
karr serve
```

Open the address in a browser and sign in with the value of `KARR_ADMIN_TOKEN`;
the SPA keeps it in `sessionStorage` for the tab and sends it as a bearer token.
Anything but a loopback deployment must sit behind a TLS terminator (in
kitt-stack that is Traefik): the admin token and the one-time registration
tokens in install commands travel in every request. Set `KARR_ENABLE_HSTS=true`
once TLS is in place. [docs/usage.md](docs/usage.md) walks through the first
agent and environment; [docs/api.md](docs/api.md) is the API reference.

### Configuration

Every value is read from the environment, or from OpenBao when `OPENBAO_ADDR`
and `OPENBAO_TOKEN` are set (see flag-commons). `.env.example` lists them all.

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | *(required)* | PostgreSQL URL; `postgres://` and `postgresql://` are normalised to psycopg. Use `sslmode=require` off-host. |
| `KARR_ADMIN_TOKEN` | *(required)* | Bearer token for `/api/v1/*` and the SPA; at least 16 characters. |
| `KARR_SECRET_KEY` | *(required)* | Fernet key that encrypts agent tokens at rest. |
| `KARR_PUBLIC_URL` | | Public base URL written into install commands; provisioning answers 503 until it is set. Validated at boot. |
| `LISTEN_ADDR` | `:8080` | Bind address. |
| `LOG_LEVEL` / `LOG_FORMAT` | `info` / `text` | slog-compatible logging; `json` for the stack. |
| `KARR_CORS_ORIGINS` | | Comma-separated explicit origins (never `*`); only needed for the Vite dev server. |
| `KARR_TRUSTED_PROXIES` | | CIDRs whose `X-Forwarded-*` headers are trusted; rate limits key on the direct peer otherwise. |
| `KARR_REGISTRATION_TTL` | `3600` | Lifetime of a provisioned registration token, max 7 days. |
| `KARR_RECONCILE_INTERVAL` | `30` | Seconds between reconciliation passes over online agents. |
| `KARR_RECONCILE_TIMEOUT` | `20` | Per-agent budget (BONNIE call plus database write) inside one pass. |
| `KARR_DEFAULT_AGENT_URL` / `_TOKEN` | | Seed one agent at boot (best effort). |
| `KARR_ENABLE_HSTS` | `false` | Send `Strict-Transport-Security`; turn on behind TLS. |
| `KARR_ALLOW_INSECURE_INSTALL` | `false` | Allow a plain-http `KARR_PUBLIC_URL` for labs without TLS. |

### Docker

The image builds the frontend and the service in one multi-stage `Dockerfile`
(non-root, `HEALTHCHECK` on `/health`). `docker-compose.yml` runs PostgreSQL and
KARR locally, with an `observability` profile that adds Prometheus and Grafana
provisioned with `grafana/dashboards/karr-overview.json`:

```bash
cp .env.example .env            # fill KARR_ADMIN_TOKEN, KARR_SECRET_KEY, GF_ADMIN_PASSWORD (POSTGRES_PASSWORD has a dev default)
docker compose up -d postgres karr
docker compose --profile observability up -d
```

Provisioning needs `KARR_PUBLIC_URL` in `.env`; for a plain-http lab run also
set `KARR_ALLOW_INSECURE_INSTALL=true`. Compose passes secrets as container
environment (visible to `docker inspect`), which is acceptable for a
development box only; production takes them from OpenBao through the stack
`.env`.

`docker-compose.dev.yml` swaps the service for `uvicorn --reload` over the
bind-mounted `src/` (`Dockerfile.dev`); pair it with `npm run dev` in
`frontend/`.

Production runs from the kitt-stack compose in the infrastructure repository,
updated through Portainer; see the FLAG documentation in the vault.

## Development

```bash
poetry install --with dev
make lint          # ruff check, ruff format --check, mypy
make test          # unit + contract tests, no database needed
make security      # bandit, pip-audit
TEST_DATABASE_URL=postgresql://karr:pw@localhost:5432/karr_test make test-all
```

The integration suite creates and drops the `karr_*` tables in the database it
is given; CI runs it against a PostgreSQL 17 service and enforces 85 % coverage.
The contract suite replays the 87 fixtures recorded from the Go service; every
intentional difference is annotated with its K-D id in `tests/contract/README.md`.

### Frontend

The SPA lives in `frontend/` (React 19, react-router 7, TanStack Query 5,
Vite 6, TypeScript strict, Vitest). The Docker build compiles it and copies
`dist/` into `src/karr/web/static/`, which the service serves with an
`index.html` fallback. Locally, `make frontend` runs the checks, builds and
installs it; `npm run dev` starts Vite on port 5173 and proxies `/api`,
`/health`, `/ready` and `/metrics` to a `karr serve` on port 8080.

### Observability

`/metrics` exposes `karr_http_requests_total` and
`karr_http_request_duration_seconds` by route template, `karr_build_info`, and
the `process_*`, `python_*` collectors. The Grafana dashboard shows request rate
and p95 latency by route, status classes, RSS and CPU, open file descriptors
and Python GC activity, in Catppuccin Mocha, selected by the Prometheus `job`
variable. `/ready` reports the database (critical), `bonnie-agents` and
`reconciler` (informational); it runs a real database round trip per call and
is unauthenticated, so keep it behind the platform's ingress limits.

### API docs

`docs/api.md` is generated: `make api-docs` (a unit test fails when it is stale).

## License

Apache 2.0
