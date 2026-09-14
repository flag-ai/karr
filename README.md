# KARR

**Kirizan's AI Refinement Runtime** — the FLAG control plane that provisions AI
development environments on GPU hosts running [BONNIE](https://github.com/flag-ai/bonnie).

> **Rewrite in progress.** This tree replaces the Go service, preserved at tag
> `go-final-0.2.2`. It is a Python port with the same routes, schema and SPA,
> plus the defect fixes listed in `docs/changelog.md`.

## Run

```bash
export DATABASE_URL=postgresql://karr:karr@localhost:5432/karr
export KARR_ADMIN_TOKEN=...      # API bearer token
export KARR_SECRET_KEY=...       # Fernet key: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
karr migrate up
karr serve
```

Open the address in a browser and sign in with the value of `KARR_ADMIN_TOKEN`;
the SPA keeps it in `sessionStorage` for the tab and sends it as a bearer token.
Anything but a loopback deployment must sit behind a TLS terminator (in
kitt-stack that is Traefik): the admin token and the one-time registration
tokens in install commands travel in every request. Set `KARR_ENABLE_HSTS=true`
once TLS is in place.

## Development

```bash
poetry install --with dev
poetry run pytest tests/unit
poetry run ruff check src tests && poetry run ruff format --check src tests
poetry run mypy
```

### Frontend

The SPA lives in `frontend/` (React 19, react-router 7, TanStack Query 5,
Vite 6, TypeScript strict, Vitest). The Docker build compiles it and copies
`dist/` into `src/karr/web/static/`, which the service serves with an
`index.html` fallback. For a local run:

```bash
cd frontend
npm ci
npm run lint && npm run typecheck && npm test -- --run
npm run build && rm -rf ../src/karr/web/static/assets && cp -r dist/. ../src/karr/web/static/
```

`npm run dev` starts Vite on port 5173 and proxies `/api`, `/health`, `/ready`
and `/metrics` to a `karr serve` on port 8080.

## License

Apache 2.0
