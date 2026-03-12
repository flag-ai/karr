# KARR Architecture

## FLAG Platform Context

KARR (Kirizan's AI Refinement Runtime) is part of the **FLAG (Foundation for Local AI Governance)** platform. FLAG provides a self-hosted AI infrastructure stack:

- **KARR** — model creation and fine-tuning workbench (this project)
- **KITT** — inference engine testing and benchmarking suite
- **BONNIE** — GPU host agent for container and hardware management
- **DEVON** — model discovery and management
- **flag-commons** — shared Go library for config, secrets, health, logging, database, and versioning

All components communicate over HTTP and share infrastructure patterns via flag-commons.

## KARR's Role

KARR is the control plane for AI development environments. It provides a web UI and REST API for managing GPU-backed containers across multiple hosts. KARR never touches hardware directly — all GPU and container operations are proxied through BONNIE agents running on remote GPU hosts.

## Component Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        KARR Server                           │
│                                                              │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────────────┐ │
│  │  Chi Router  │  │  Middleware  │  │   Embedded SPA       │ │
│  │  (api pkg)   │──│  CORS       │  │   (React 19)         │ │
│  └──────┬───────┘  │  Security   │  └──────────────────────┘ │
│         │          │  Logging    │                            │
│         │          │  Recovery   │                            │
│         │          └─────────────┘                            │
│         │                                                    │
│  ┌──────▼───────┐  ┌─────────────┐  ┌──────────────────────┐ │
│  │   Handlers   │──│  Services   │──│  BONNIE Registry     │ │
│  │              │  │  AgentSvc   │  │  Client pool         │ │
│  │              │  │  ProjectSvc │  │  Health loop (30s)   │ │
│  │              │  │  EnvSvc     │  └──────────┬───────────┘ │
│  └──────────────┘  └──────┬──────┘             │             │
│                    ┌──────▼──────┐    ┌────────▼──────────┐  │
│                    │  sqlc/pgx   │    │  BONNIE HTTP      │  │
│                    │  (DB layer) │    │  Clients           │  │
│                    └──────┬──────┘    └────────┬───────────┘  │
└───────────────────────────┼────────────────────┼─────────────┘
                            │                    │
                   ┌────────▼────────┐  ┌────────▼────────┐
                   │  PostgreSQL 17  │  │  BONNIE Agents   │
                   └─────────────────┘  │  (GPU Hosts)     │
                                        └─────────────────┘
```

## Request Flow

1. **HTTP Request** arrives at the Chi router
2. **Middleware chain** processes the request (recovery, security headers, logging, CORS)
3. **Handler** validates input and delegates to a service
4. **Service** implements business logic, queries the database via sqlc, and interacts with BONNIE agents via the registry
5. **BONNIE Registry** resolves the agent UUID to an HTTP client and forwards the operation
6. **Response** flows back through the handler (JSON serialization) and middleware (headers)

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| BONNIE agent proxy | KARR is stateless w.r.t. GPU hardware; agents own their host |
| sqlc (no ORM) | Type-safe SQL with zero runtime overhead |
| Embedded SPA | Single binary deployment — no separate web server needed |
| Interface-first services | Handlers depend on service interfaces for testability |
| Health registry pattern | Extensible readiness checks (DB + BONNIE agents) via flag-commons |
| OpenBao with env fallback | Production secrets management with simple local development |

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
| Theme | Catppuccin Mocha |
