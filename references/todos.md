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

## Suggestions

- **Improve SSE log line escaping** — `internal/api/handlers/environment.go:148` — only newlines are escaped, carriage returns and colons are not
- **Add token rotation/expiration for agent tokens** — no expiry or audit trail currently
- **Use GitHub Secrets for CI test credentials** — `.github/workflows/ci.yml:58` — hardcoded test password

---

## Completed

_(none yet)_
