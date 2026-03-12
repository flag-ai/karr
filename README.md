# KARR

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

**Kirizan's AI Refinement Runtime** — the model creation and fine-tuning workbench in the [FLAG (Foundation for Local AI Governance)](https://github.com/flag-ai) platform. KARR provides a web UI for managing AI development environments across BONNIE-managed GPU hosts.

KARR is one of several FLAG components that work together to provide a self-hosted AI infrastructure stack. [BONNIE](https://github.com/flag-ai/bonnie) agents run on GPU hosts, [KITT](https://github.com/flag-ai/kitt) handles inference benchmarking, and [DEVON](https://github.com/flag-ai/devon) manages model discovery. All components share infrastructure patterns via [flag-commons](https://github.com/flag-ai/commons).

## Architecture

```
┌──────────────┐     HTTP      ┌──────────────┐     HTTP      ┌──────────────┐
│  KARR Web UI │ ◄──────────► │  KARR Server  │ ◄──────────► │ BONNIE Agent │
│ (React SPA)  │              │   (Go API)    │              │  (GPU Host)  │
└──────────────┘              └──────┬───────┘              └──────────────┘
                                     │
                                     │ pgx
                                     ▼
                              ┌──────────────┐
                              │ PostgreSQL 17 │
                              └──────────────┘
```

KARR never touches hardware directly — all GPU/container operations go through BONNIE agents over HTTP.

## Tech Stack

- **Backend:** Go 1.25, Chi router, sqlc, PostgreSQL 17
- **Frontend:** React 19, TypeScript, Vite, TanStack Query
- **Shared libraries:** [flag-commons](https://github.com/flag-ai/commons)
- **Containerization:** Docker multi-stage build (Alpine)
- **Monitoring:** Prometheus metrics at `/metrics`
- **Theme:** [Catppuccin Mocha](https://github.com/catppuccin/catppuccin)

## Prerequisites

- Go 1.25+
- Node.js 22+
- Docker & Docker Compose
- PostgreSQL 17 (or use docker-compose)
- sqlc (for code generation)

## Quick Start

```bash
# Start Postgres
docker compose up -d postgres

# Run migrations and start the server
go run ./cmd/karr migrate up
go run ./cmd/karr serve

# Frontend development (separate terminal)
cd web && npm install && npm run dev
```

The API is available at `http://localhost:8080` and the dev frontend at `http://localhost:5173`.

## Configuration

All configuration is via environment variables (or OpenBao secrets):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | — | PostgreSQL connection string |
| `LOG_LEVEL` | No | `info` | debug, info, warn, error |
| `LOG_FORMAT` | No | `text` | text or json |
| `LISTEN_ADDR` | No | `:8080` | HTTP listen address |
| `KARR_DEFAULT_AGENT_URL` | No | — | Auto-register a BONNIE agent on startup |
| `KARR_DEFAULT_AGENT_TOKEN` | No | — | Bearer token for the default agent |
| `KARR_CORS_ORIGINS` | No | — | Comma-separated allowed CORS origins |

See `.env.example` for all options.

## BONNIE Agent Registration

Register a BONNIE agent via the API:

```bash
curl -X POST http://localhost:8080/api/v1/agents \
  -H 'Content-Type: application/json' \
  -d '{"name":"gpu-host-1","url":"http://gpu-host:7777","token":"your-bonnie-token"}'
```

Or set `KARR_DEFAULT_AGENT_URL` and `KARR_DEFAULT_AGENT_TOKEN` to auto-register on startup.

## API Routes

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness check |
| GET | `/ready` | Readiness check (DB) |
| GET | `/metrics` | Prometheus metrics |
| GET/POST | `/api/v1/agents` | List/create agents |
| GET/DELETE | `/api/v1/agents/{id}` | Get/delete agent |
| GET | `/api/v1/agents/{id}/status` | Live GPU + system info |
| GET/POST | `/api/v1/projects` | List/create projects |
| GET/PUT/DELETE | `/api/v1/projects/{id}` | Get/update/delete project |
| GET/POST | `/api/v1/environments` | List/create environments |
| GET/DELETE | `/api/v1/environments/{id}` | Get/remove environment |
| POST | `/api/v1/environments/{id}/start` | Start environment |
| POST | `/api/v1/environments/{id}/stop` | Stop environment |
| GET | `/api/v1/environments/{id}/logs` | Stream logs (SSE) |

## Development

```bash
make dev           # Start Postgres
make test          # Unit tests with coverage
make test-integration  # Integration tests (needs Postgres)
make lint          # golangci-lint
make sqlc          # Regenerate sqlc code
make build         # Build Go binary
make build-web     # Build frontend
make docker        # Docker compose build
```

## Full Stack (Docker)

```bash
docker compose up
```

Dashboard at `http://localhost:8080`, Prometheus at `http://localhost:9090`, Grafana at `http://localhost:3000`.

## License

Apache 2.0
