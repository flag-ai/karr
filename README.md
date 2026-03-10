# KARR

**Kirizan's AI Refinement Runtime** — a web-based tool that creates AI Dev environments by orchestrating Bonnie agents on remote GPU hosts.

## Tech Stack

- **Backend:** Go 1.25, PostgreSQL 17
- **Frontend:** React, TypeScript, Vite
- **Shared libraries:** [flag-commons](https://github.com/flag-ai/commons)
- **Containerization:** Docker multi-stage build

## Prerequisites

- Go 1.25+
- Node.js 22+
- Docker & Docker Compose
- PostgreSQL 17 (or use docker-compose)

## Development

```bash
# Start Postgres
docker compose up -d postgres

# Run migrations
go run ./cmd/karr migrate up

# Start the server
go run ./cmd/karr serve

# Frontend development
cd web
npm install
npm run dev
```

## License

Apache 2.0
