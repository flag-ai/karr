# KARR API Reference

Generated from the OpenAPI schema (`karr openapi`); do not edit by hand, run
`make api-docs`. Base URL in kitt-stack: `https://karr.internal.kirby.network`.

**Authentication.** Routes marked *admin* need `Authorization: Bearer <KARR_ADMIN_TOKEN>`.
`/health`, `/ready`, `/metrics`, `/api/v1/install.sh` and `/api/v1/agents/register`
are open; the last two are gated by a one-time registration token instead.

**Errors.** Every error body is `{"error": "<message>"}`: 400 for a missing or
malformed JSON body, 422 for a body that fails validation (the message names the
field), 401 without a valid bearer, 404 for an unknown id, 409 for a state
conflict, 413 past the 1 MiB body limit, 429 when a rate limit trips (the
token-bucket limits add `Retry-After`) or too many log streams are open, 502
when BONNIE refuses an operation, 503 when provisioning is not configured.

**Omitted fields.** Optional response fields (`project_id`, `container_id`,
`status_message`, `last_seen_at`, `claimed_at`, `agent_id`, empty `env`/`mounts`/
`command`) are absent rather than `null`, as in the Go service.


## Health

### GET /health

Liveness only; never touches a dependency.

**Response 200** — `object`

### GET /ready

Runs every registered check. `database` is critical; `bonnie-agents` and `reconciler` are informational, so an empty control plane is still ready. 503 when a critical check fails.

**Response 200** — `application/json`


## Metrics

### GET /metrics

Prometheus text: `karr_http_requests_total`, `karr_http_request_duration_seconds`, `karr_build_info`, plus the `process_*`, `python_*` collectors.

**Response 200** — `application/json`


## Auth

### GET /api/v1/auth/check *(admin)*

204 with a valid token, 401 otherwise. The SPA's sign-in form calls it, so it is rate limited per client (429).

**Response 204** — no body


## Agent provisioning

### POST /api/v1/agents/provision *(admin)*

Creates a pending registration and returns the one-shot install command; 503 until `KARR_PUBLIC_URL` is set. Rate limited per client.

**Request body** — `ProvisionRequest`

| Field | Type | Required | Notes |
|---|---|---|---|
| `label` | string | yes | max 200 chars |

**Response 201** — `ProvisionOut`

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string (uuid) | yes |  |
| `token` | string | yes |  |
| `install_command` | string | yes |  |
| `expires_at` | string | yes |  |

### GET /api/v1/agents/registrations *(admin)*

**Response 200** — `RegistrationOut[]`

### DELETE /api/v1/agents/registrations/{registration_id} *(admin)*

404 for an unknown id.

**Response 204** — no body


## Agent installation

### GET /api/v1/install.sh

Query `token=<registration token>`. Serves the BONNIE installer only for a pending, unexpired registration: 400 for a missing or malformed token, 404 for an unknown one, 410 once it is claimed or expired. Plain-http server URLs need `KARR_ALLOW_INSECURE_INSTALL`.

**Response 200** — no body

### POST /api/v1/agents/register

Called by the installer with the registration token; claims it and creates the agent in one transaction. 400 for a malformed body, 422 with a generic `registration failed` for an unknown, expired or already claimed token and for a label that clashes with an existing agent name (the same codes as the Go service, since BONNIE's installer consumes them). Rate limited per client; `X-Forwarded-For` is honoured only from `KARR_TRUSTED_PROXIES`.

**Response 200** — `application/json`


## Agents

### GET /api/v1/agents *(admin)*

**Response 200** — `AgentOut[]`

### POST /api/v1/agents *(admin)*

`url` must be an http(s) URL without credentials; 409 when the name exists.

**Request body** — `AgentCreate`

| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | string | yes |  |
| `url` | string | yes |  |
| `token` | string | no |  |

**Response 201** — `AgentOut`

### GET /api/v1/agents/{agent_id} *(admin)*

**Response 200** — `AgentOut`

### DELETE /api/v1/agents/{agent_id} *(admin)*

409 while environments reference the agent unless `force=true`, which removes their containers on BONNIE first and then the rows; if a container cannot be removed the rows are kept and the call answers 409 naming the environments.

| Query | Type | Required | Notes |
|---|---|---|---|
| `force` | boolean | no |  |

**Response 204** — no body

### GET /api/v1/agents/{agent_id}/status *(admin)*

`system` and `gpu` are present only while the agent is online and BONNIE answered; `gpu.gpus` can be `null` on hosts without a GPU.

**Response 200** — `AgentStatusOut`

| Field | Type | Required | Notes |
|---|---|---|---|
| `agent` | AgentOut | yes |  |
| `system` | SystemInfoResponse, nullable | no |  |
| `gpu` | GPUSnapshot, nullable | no |  |


## Projects

### GET /api/v1/projects *(admin)*

**Response 200** — `ProjectOut[]`

### POST /api/v1/projects *(admin)*

409 when the name exists.

**Request body** — `ProjectCreate`

| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | string | yes |  |
| `description` | string | no |  |

**Response 201** — `ProjectOut`

### GET /api/v1/projects/{project_id} *(admin)*

**Response 200** — `ProjectOut`

### PUT /api/v1/projects/{project_id} *(admin)*

A `null` or absent field is left unchanged.

**Request body** — `ProjectUpdate`

| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | string, nullable | no |  |
| `description` | string, nullable | no |  |

**Response 200** — `ProjectOut`

### DELETE /api/v1/projects/{project_id} *(admin)*

Environments keep running and lose their `project_id`.

**Response 204** — no body


## Environments

### GET /api/v1/environments *(admin)*

**Response 200** — `EnvironmentOut[]`

### POST /api/v1/environments *(admin)*

400 for an unknown `agent_id` or `project_id`; 409 when the name exists on that agent. The row is created first, then the container; a BONNIE failure leaves the row in `error` with `status_message` and answers 502.

**Request body** — `EnvironmentCreate`

| Field | Type | Required | Notes |
|---|---|---|---|
| `agent_id` | string (uuid) | yes |  |
| `project_id` | string (uuid), nullable | no |  |
| `name` | string | yes |  |
| `image` | string | yes |  |
| `gpu` | boolean | no | default `false` |
| `env` | string[] | no |  |
| `mounts` | string[] | no |  |
| `command` | string[] | no |  |

**Response 201** — `EnvironmentOut`

### GET /api/v1/environments/{env_id} *(admin)*

**Response 200** — `EnvironmentOut`

### DELETE /api/v1/environments/{env_id} *(admin)*

Removes the container, then the row. 409 while a create is in flight; a container BONNIE no longer knows about is dropped once the reconciler has marked it missing.

**Response 204** — no body

### POST /api/v1/environments/{env_id}/start *(admin)*

409 unless the environment is `stopped`.

**Response 204** — no body

### POST /api/v1/environments/{env_id}/stop *(admin)*

409 unless the environment is `running`.

**Response 204** — no body

### GET /api/v1/environments/{env_id}/logs *(admin)*

SSE relay of the container logs (K-D2): keepalives, `event: end`, `event: error`.

`text/event-stream`. Each log line is one `data:` frame with backslash, CR and LF escaped as `\\`, `\r`, `\n`; `: keepalive` every 15 s; `event: end` when the container's stream closes (or after the 4 h stream limit), `event: error` with a message on failure. 409 when the environment has no container, 429 past 8 concurrent streams per agent or 3 per client.

**Response 200** — `text/event-stream`
