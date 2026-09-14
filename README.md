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

## Development

```bash
poetry install --with dev
poetry run pytest tests/unit
poetry run ruff check src tests && poetry run ruff format --check src tests
poetry run mypy
```

## License

Apache 2.0
