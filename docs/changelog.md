# Changelog

## 0.3.0

Python rewrite of the Go service (preserved at tag `go-final-0.2.2`). Same
routes, schema and SPA; the defects fixed are listed by K-D id in the FLAG
Python Rewrite Plan and summarised here as the service PRs land.

- K1: scaffold, admin bearer auth (K-D1), error envelope with 413/422 (K-D5,
  K-D19), CSP/HSTS headers (K-D15), CORS `max_age` (K-D14), non-root image with
  `HEALTHCHECK` (K-D16), Fernet token cipher (K-D12).
- K2: Alembic baseline with `token_encrypted` (K-D12), `last_checked_at`
  (K-D10), `ON DELETE RESTRICT` plus `?force=true` on agent delete (K-D4),
  `UNIQUE (agent_id, name)` (K-D22), CHECK constraints; 409/422/404 instead of
  500/204 (K-D5); agent URL scheme validation (K-D13); registry polls at start
  and reloads periodically, `bonnie-agents` is non-critical (K-D9).
- K3: provisioning with the TTL from `KARR_REGISTRATION_TTL` and `expired`
  computed on read (K-D8); `install.sh` served only for a pending, unexpired
  token (K-D7); registration claim and agent insert in one transaction with
  `X-Forwarded-For` trusted only from `KARR_TRUSTED_PROXIES` (K-D6); the
  registrant's address is validated like an admin-supplied URL (K-D13); per-
  client rate limits on the provisioning routes (K-D23); the control-plane URL
  comes from `KARR_PUBLIC_URL` or a trusted proxy, never the `Host` header.
