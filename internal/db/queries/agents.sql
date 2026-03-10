-- name: ListAgents :many
SELECT * FROM karr_agents ORDER BY name;

-- name: GetAgent :one
SELECT * FROM karr_agents WHERE id = $1;

-- name: GetAgentByName :one
SELECT * FROM karr_agents WHERE name = $1;

-- name: CreateAgent :one
INSERT INTO karr_agents (name, url, token, status)
VALUES ($1, $2, $3, $4)
RETURNING *;

-- name: UpdateAgent :one
UPDATE karr_agents
SET name = $2, url = $3, token = $4, updated_at = now()
WHERE id = $1
RETURNING *;

-- name: DeleteAgent :exec
DELETE FROM karr_agents WHERE id = $1;

-- name: UpdateAgentStatus :exec
UPDATE karr_agents
SET status = $2, last_seen_at = $3, updated_at = now()
WHERE id = $1;
