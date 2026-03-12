# KARR Architecture Reference

Internal architecture reference for developers working on KARR.

## Component Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                        KARR Server                           │
│                                                              │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────────────┐ │
│  │  Chi Router  │  │  Middleware  │  │   Embedded SPA       │ │
│  │  (api pkg)   │──│  CORS/Auth  │  │   (web/dist)         │ │
│  └──────┬───────┘  │  Logging    │  └──────────────────────┘ │
│         │          │  Recovery   │                            │
│         │          │  Security   │                            │
│         │          └─────────────┘                            │
│         │                                                    │
│  ┌──────▼───────┐  ┌─────────────┐  ┌──────────────────────┐ │
│  │   Handlers   │──│  Services   │──│  BONNIE Registry     │ │
│  │  health      │  │  agent      │  │  (agent clients)     │ │
│  │  agent       │  │  project    │  │  health loop (30s)   │ │
│  │  project     │  │  environment│  └──────────────────────┘ │
│  │  environment │  └──────┬──────┘                           │
│  │  metrics     │         │                                  │
│  └──────────────┘  ┌──────▼──────┐                           │
│                    │  sqlc/pgx   │                            │
│                    │  (DB layer) │                            │
│                    └──────┬──────┘                            │
└───────────────────────────┼──────────────────────────────────┘
                            │
                   ┌────────▼────────┐
                   │  PostgreSQL 17  │
                   └─────────────────┘
```

## Package Layout

```
cmd/karr/                   Entry point, CLI commands (serve, migrate)
internal/
  api/
    handlers/               HTTP handlers (health, agent, project, environment, metrics)
    middleware/              CORS, security headers, logging, panic recovery
    router.go               Chi router setup, route registration
  bonnie/
    client.go               BONNIE HTTP client interface + implementation
    registry.go             Agent registry with health polling loop
    health.go               Agent availability check for health registry
    types.go                BONNIE domain types (GPU, containers, system info)
  config/
    config.go               KARR-specific config (extends flag-commons Base)
  db/
    db.go                   PostgreSQL connection pool management
    sqlc/                   Generated query code (sqlc)
  models/                   Domain types (Agent, Project, Environment)
  service/
    agent.go                Agent CRUD + status
    project.go              Project CRUD
    environment.go          Environment lifecycle (create, start, stop, remove, logs)
migrations/                 SQL migration files (golang-migrate)
web/                        React 19 / TypeScript / Vite frontend
tests/                      Integration tests
```

## Data Flow

1. **HTTP Request** → Chi router → middleware chain → handler
2. **Handler** → validates input → calls service method
3. **Service** → business logic → queries DB via sqlc → interacts with BONNIE registry
4. **BONNIE Registry** → resolves agent UUID → delegates to BONNIE HTTP client
5. **BONNIE Client** → HTTP call to remote GPU host agent → returns result
6. **Response** → handler serializes JSON → middleware adds headers → client

## Key Design Decisions

- **KARR never touches hardware directly** — all GPU/container operations proxy through BONNIE agents
- **sqlc for type-safe SQL** — no ORM, generated Go code from SQL queries
- **flag-commons for infrastructure** — shared health, config, secrets, logging, database, version
- **Embedded SPA** — React frontend compiled into Go binary via `//go:embed`
- **Interface-first services** — handlers depend on service interfaces, enabling test mocks
- **Health registry pattern** — extensible health checks (database, BONNIE agents) via commons

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Go 1.25 |
| Router | Chi v5 |
| Database | PostgreSQL 17 via pgx/v5 |
| Query Gen | sqlc |
| Migrations | golang-migrate |
| Frontend | React 19, TypeScript, Vite |
| Secrets | OpenBao (env var fallback) |
| Monitoring | Prometheus, Grafana |
| Shared Lib | github.com/flag-ai/commons |
| CI | GitHub Actions |
| Container | Multi-stage Docker (Alpine) |
