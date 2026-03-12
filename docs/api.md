# KARR API Reference

Base URL: `http://localhost:8080`

## Health & Metrics

### GET /health

Liveness check. Does not probe dependencies.

**Response 200**
```json
{
  "status": "ok",
  "version": "0.1.0 (abc1234, 2026-03-01)"
}
```

### GET /ready

Readiness check. Verifies database connectivity and at least one BONNIE agent is online.

**Response 200** (all checks pass)
```json
{
  "healthy": true,
  "version": "0.1.0 (abc1234, 2026-03-01)",
  "checks": [
    {"name": "database", "healthy": true, "latency_ms": 2},
    {"name": "bonnie-agents", "healthy": true, "latency_ms": 1}
  ]
}
```

**Response 503** (one or more checks fail)
```json
{
  "healthy": false,
  "version": "0.1.0 (abc1234, 2026-03-01)",
  "checks": [
    {"name": "database", "healthy": true, "latency_ms": 2},
    {"name": "bonnie-agents", "healthy": false, "error": "no online agents (1 registered, all offline)", "latency_ms": 5}
  ]
}
```

### GET /metrics

Prometheus metrics endpoint.

---

## Agents

### POST /api/v1/agents

Register a BONNIE agent.

**Request**
```json
{
  "name": "gpu-host-1",
  "url": "http://gpu-host:7777",
  "token": "bearer-token"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Display name |
| `url` | string | yes | BONNIE agent base URL |
| `token` | string | no | Bearer token for authentication |

**Response 201**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "gpu-host-1",
  "url": "http://gpu-host:7777",
  "status": "offline",
  "last_seen_at": null,
  "created_at": "2026-03-12T10:00:00Z",
  "updated_at": "2026-03-12T10:00:00Z"
}
```

> Token is never returned in responses.

### GET /api/v1/agents

List all registered agents.

**Response 200**
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "gpu-host-1",
    "url": "http://gpu-host:7777",
    "status": "online",
    "last_seen_at": "2026-03-12T10:05:00Z",
    "created_at": "2026-03-12T10:00:00Z",
    "updated_at": "2026-03-12T10:05:00Z"
  }
]
```

### GET /api/v1/agents/{id}

Get a single agent by UUID.

**Response 200** — same shape as list item above.

**Response 404**
```json
{"error": "agent not found"}
```

### GET /api/v1/agents/{id}/status

Get live system and GPU info from the agent. Fields `system` and `gpu` may be `null` if the agent is unreachable.

**Response 200**
```json
{
  "agent": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "gpu-host-1",
    "url": "http://gpu-host:7777",
    "status": "online",
    "last_seen_at": "2026-03-12T10:05:00Z",
    "created_at": "2026-03-12T10:00:00Z",
    "updated_at": "2026-03-12T10:05:00Z"
  },
  "system": {
    "cpu_cores": 16,
    "cpu_percent": 23.5,
    "memory_total": 68719476736,
    "memory_available": 34359738368,
    "memory_percent": 50.0
  },
  "gpu": {
    "gpus": [
      {
        "index": 0,
        "name": "NVIDIA RTX 4090",
        "memory_total": 24576,
        "memory_allocated": 8192,
        "memory_free": 16384,
        "utilization": 0.35
      }
    ]
  }
}
```

### DELETE /api/v1/agents/{id}

Remove an agent. **Response 204** (no body).

---

## Projects

### POST /api/v1/projects

Create a project.

**Request**
```json
{
  "name": "llama-finetune",
  "description": "Fine-tuning Llama 3 on custom dataset"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Project name |
| `description` | string | no | Project description |

**Response 201**
```json
{
  "id": "660e8400-e29b-41d4-a716-446655440000",
  "name": "llama-finetune",
  "description": "Fine-tuning Llama 3 on custom dataset",
  "created_at": "2026-03-12T10:00:00Z",
  "updated_at": "2026-03-12T10:00:00Z"
}
```

### GET /api/v1/projects

List all projects. **Response 200** — array of project objects.

### GET /api/v1/projects/{id}

Get a single project. **Response 200** — project object.

### PUT /api/v1/projects/{id}

Update a project. Only provided fields are updated.

**Request**
```json
{
  "name": "llama-finetune-v2",
  "description": "Updated description"
}
```

**Response 200** — updated project object.

### DELETE /api/v1/projects/{id}

Delete a project. **Response 204** (no body).

---

## Environments

### POST /api/v1/environments

Create an AI development environment (container on a BONNIE host).

**Request**
```json
{
  "name": "training-env",
  "image": "pytorch/pytorch:2.2.0-cuda12.1-cudnn8-devel",
  "agent_id": "550e8400-e29b-41d4-a716-446655440000",
  "project_id": "660e8400-e29b-41d4-a716-446655440000",
  "gpu": true,
  "env": ["WANDB_API_KEY=...", "HF_TOKEN=..."],
  "mounts": ["/data/models:/models:ro"],
  "command": ["python", "train.py"]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Environment name |
| `image` | string | yes | Container image |
| `agent_id` | uuid | yes | Target BONNIE agent |
| `project_id` | uuid | no | Associated project |
| `gpu` | boolean | no | Enable GPU passthrough (default: false) |
| `env` | string[] | no | Environment variables |
| `mounts` | string[] | no | Volume mounts |
| `command` | string[] | no | Container command |

**Response 201**
```json
{
  "id": "770e8400-e29b-41d4-a716-446655440000",
  "name": "training-env",
  "image": "pytorch/pytorch:2.2.0-cuda12.1-cudnn8-devel",
  "agent_id": "550e8400-e29b-41d4-a716-446655440000",
  "project_id": "660e8400-e29b-41d4-a716-446655440000",
  "container_id": "abc123def456",
  "status": "stopped",
  "gpu": true,
  "env": ["WANDB_API_KEY=...", "HF_TOKEN=..."],
  "mounts": ["/data/models:/models:ro"],
  "command": ["python", "train.py"],
  "created_at": "2026-03-12T10:00:00Z",
  "updated_at": "2026-03-12T10:00:00Z"
}
```

### GET /api/v1/environments

List all environments. **Response 200** — array of environment objects.

### GET /api/v1/environments/{id}

Get a single environment. **Response 200** — environment object.

### POST /api/v1/environments/{id}/start

Start an environment's container. **Response 204** (no body).

### POST /api/v1/environments/{id}/stop

Stop an environment's container. **Response 204** (no body).

### DELETE /api/v1/environments/{id}

Remove an environment and its container. **Response 204** (no body).

### GET /api/v1/environments/{id}/logs

Stream container logs via Server-Sent Events (SSE).

**Response 200** (`text/event-stream`)
```
data: Starting training...
data: Epoch 1/10: loss=2.345
data: Epoch 2/10: loss=1.892
```

---

## Error Responses

All endpoints return errors in a consistent format:

```json
{"error": "descriptive error message"}
```

| Status | Meaning |
|--------|---------|
| 400 | Bad request — invalid JSON or missing required fields |
| 404 | Resource not found |
| 500 | Internal server error |
