# Pending Fixes

Tracked by the `/pr-review` skill. After fixing an item, move it to the **Completed** section with the PR number.

## Priority Levels

- **Must Fix** — fix before merging the current PR, no exceptions
- **Should Fix** — fix in the next PR, even if that PR doesn't touch the affected files
- **Suggestions** — fix when the affected file(s) are next touched

---

## Must Fix

_(none)_

## Should Fix

- **Add authentication middleware to API v1 routes** — `internal/api/router.go:46` — all endpoints are unauthenticated (Phase 1 limitation, must be addressed before any deployment)
- **Validate agent URL scheme** — `internal/bonnie/client.go:47` — accept only `http://` and `https://`, reject `file://` and private IPs to prevent SSRF
- **Use `sslmode=require` for production database connections** — `docker-compose.yml:28`, `.env.example` — currently `sslmode=disable`
- **Hash agent tokens at rest** — `internal/service/agent.go:106` — tokens stored in plaintext in the database
- **Add Content-Security-Policy and HSTS headers** — `internal/api/middleware/security.go` — missing CSP, HSTS, Permissions-Policy
- **Validate response Content-Type in frontend API client** — `web/src/api/client.ts:16` — blindly deserializes as JSON
- **Run Docker container as non-root user** — `Dockerfile` — add `USER` directive
- **`agentFromRow` should not populate Token field** — `internal/service/convert.go:48` — token is copied then manually stripped in every caller; fragile if a new caller forgets
- **Add confirmation dialogs for destructive actions** — `web/src/pages/Agents.tsx:88`, `Projects.tsx:118`, `Environments.tsx:138` — Remove/Delete buttons fire immediately
- **Add error handling to delete/start/stop mutations** — `web/src/pages/Agents.tsx:30`, `Projects.tsx:39`, `Environments.tsx:39-52` — failures silently swallowed
- **Cap LogStream line buffer** — `web/src/components/LogStream.tsx:19` — unbounded array growth will exhaust browser memory on long-running containers
- **Fix stale BUILD_DATE in docker-compose.yml** — `docker-compose.yml:24` — hardcoded `2024-01-01`
- **Remove unnecessary gcc/musl-dev from Dockerfile** — `Dockerfile:11` — installed but builds with CGO_ENABLED=0
- **Fix API docs agent status response shape** — `docs/api.md:136-154` — documented fields don't match actual `SystemInfoResponse` / `GPUSnapshot` types
- **Add `t.Parallel()` to handler and service tests** — `internal/api/handlers/agent_test.go`, `project_test.go`, `environment_test.go`, `health_test.go`, `metrics_test.go`, service tests — project convention requires parallel where safe
- **Assert CORS header in integration test** — `tests/integration/api_test.go:627` — currently only logs a warning instead of failing

## Suggestions

- **Add token rotation/expiration for agent tokens** — no expiry or audit trail currently
- **Use GitHub Secrets for CI test credentials** — `.github/workflows/ci.yml:58` — hardcoded test password
- **Run health check immediately on startup** — `internal/bonnie/registry.go:120` — agents show stale status for up to 30s
- **Add `Access-Control-Max-Age` to CORS preflight** — `internal/api/middleware/cors.go:19` — browsers send preflight for every cross-origin request without it
- **Consider `DisallowUnknownFields` in JSON decoder** — `internal/api/handlers/respond.go:44` — typo'd field names pass silently
- **Set `send_interrupt = true` in `.air.toml`** — line 12 — allows graceful shutdown during dev hot reload
- **Pin Prometheus/Grafana image tags** — `docker-compose.yml:38,46` — `latest` tags risk unexpected breakage
- **Consolidate `docs/architecture.md` and `references/architecture.md`** — near-duplicate content risks drift
- **Add `aria-label` to sidebar nav** — `web/src/components/Layout.tsx:30` — screen reader accessibility
- **Add ARIA progressbar attributes to GPUCard** — `web/src/components/GPUCard.tsx:29-58` — progress bars are pure divs

---

## Completed

- **SSE log line escaping: escape `\r` in addition to `\n`** — `internal/api/handlers/environment.go:149` — PR #1
- **Request body size limit (1 MiB)** — `internal/api/handlers/respond.go:42` — PR #1
- **BONNIE client: only retry idempotent methods** — `internal/bonnie/client.go:73` — PR #1
- **BONNIE client: check HTTP status on GET responses** — `internal/bonnie/client.go:124-166` — PR #1
- **Environment Start/Stop/Remove: return 404 for not-found** — `internal/api/handlers/environment.go:88,104,120` — PR #1
- **Agent delete: DB first, then registry unregister** — `internal/service/agent.go:118` — PR #1
- **Grafana dashboard: replace non-existent metrics with working ones** — `grafana/dashboards/karr-overview.json` — PR #1
