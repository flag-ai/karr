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
- K4: environments with an explicit state machine (K-D3): `start`/`stop`
  answer 409 instead of 204 when the state does not allow them, and a
  background reconciler maps BONNIE's container list onto the rows every 30 s
  (per-agent timeout and isolation), adopting a row left `creating` by a crash
  or marking it `error`; unknown `agent_id`/`project_id` answer 400 (K-D5);
  the log stream (K-D2) resolves the row and agent before the headers (404/409
  instead of an empty 200), relays through a bounded queue with keepalives,
  escapes frames, and ends with `event: end` or `event: error`; a container
  BONNIE no longer knows about can still be deleted once the reconciler has
  marked it missing.
- K5: the SPA moves from `web/` to `frontend/` and is served from
  `src/karr/web/static/` with relative asset paths; an AuthGate asks for the
  admin token, keeps it in `sessionStorage` and sends it as a bearer (K-D1);
  the Dashboard survives `gpus: null` and a missing `disk` section (K-D17);
  every mutation confirms destructive actions and reports errors as toasts, and
  the API client rejects non-JSON bodies (K-D18); the log viewer reads the SSE
  relay over `fetch` (so the bearer can be sent), caps the buffer at 5 000
  lines, unescapes the frames, reconnects with backoff and stops on
  `event: end`/`event: error` (K-D2); clipboard fallback for plain-http pages;
  ARIA roles on the nav, progress bars, dialogs and the log; Vitest suite.
