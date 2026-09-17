# Changelog

## 0.3.0

Python rewrite of the Go service (preserved at tag `go-final-0.2.2`). Same
routes, schema and SPA; the defects fixed are listed by K-D id in the FLAG
Python Rewrite Plan and summarised here as the service PRs land.

- K1: scaffold, admin bearer auth (K-D1), error envelope with 413/422 (K-D5,
  K-D19), unknown request fields rejected (K-D21), CSP/HSTS headers (K-D15),
  CORS `max_age` (K-D14), non-root image with `HEALTHCHECK` (K-D16), Fernet
  token cipher (K-D12), every setting read through the commons `ChainProvider`
  so OpenBao mode falls back per key (K-D20).
- K2: Alembic baseline with `token_encrypted` (K-D12), `last_checked_at`
  (K-D10), `ON DELETE RESTRICT` plus `?force=true` on agent delete (K-D4),
  `UNIQUE (agent_id, name)` (K-D22), CHECK constraints; 409/422/404 instead of
  500/204 (K-D5); agent URL scheme validation (K-D13); registry polls at start
  and reloads periodically, `bonnie-agents` is non-critical (K-D9); agent
  status is `online`/`offline`/`unauthorized` and the `removed` environment
  state is gone (K-D11); `sslmode` stays configurable and the docs say to use
  `require` off-host (K-D24, documented rather than fixed).
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
  `event: end`/`event: error` (K-D2; the relay now escapes backslashes too so
  lines round-trip); `/api/v1/auth/check` is rate limited per client because
  the sign-in form posts to it; clipboard fallback for plain-http pages;
  ARIA roles on the nav, progress bars, dialogs and the log; Vitest suite.
- K6: the Grafana dashboard is rebuilt on `karr_http_*`, `process_*` and
  `python_*` metrics (the Go runtime panels are gone) with `karr_build_info`
  for the version; `docker-compose.yml` pins images and gains an
  `observability` profile, `docker-compose.dev.yml` runs `uvicorn --reload`
  through `karr.asgi:app`; `docs/api.md` is generated from the OpenAPI schema
  (`make api-docs`, kept current by a test) and `docs/usage.md` walks through
  the first agent; the README documents every setting. Follow-ups from the K4
  review: at most 8 log streams per agent and 3 per client (429 past that)
  and a 4 h stream limit, the relay's cleanup runs the moment a client disconnects, the
  reconciler runs agents 4 at a time with the database write inside the
  per-agent timeout, `KARR_RECONCILE_INTERVAL`/`KARR_RECONCILE_TIMEOUT` are
  configurable, and `/ready` carries an informational `reconciler` check.
- K7: parity sign-off. The 87 Go fixtures replay against the Python service
  in CI with every difference annotated by its K-D id; the replay surfaced
  K-D25 (Go's environment list dropped `project_id`, `env`, `mounts` and
  `command`) and records K-D26 (Go's install command lacked `bash -s --`, so
  `--address` could not be passed through the pipe), both fixed here. Contract
  fields are compared by value, the install script by its hardening lines, and
  every response is checked for leaked secrets and internal error detail. The end-to-end fake-BONNIE scenario
  (provision, install script, register, first poll, environment lifecycle with
  a streamed log, a container killed behind KARR's back, guarded agent delete)
  runs in the integration job. The register route keeps Go's 400/422 codes
  because BONNIE's installer consumes them; the API reference now says so.
