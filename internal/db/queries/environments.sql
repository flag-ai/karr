-- name: ListEnvironments :many
SELECT * FROM karr_environments ORDER BY created_at DESC;

-- name: ListEnvironmentsByAgent :many
SELECT * FROM karr_environments WHERE agent_id = $1 ORDER BY created_at DESC;

-- name: ListEnvironmentsByProject :many
SELECT * FROM karr_environments WHERE project_id = $1 ORDER BY created_at DESC;

-- name: GetEnvironment :one
SELECT * FROM karr_environments WHERE id = $1;

-- name: CreateEnvironment :one
INSERT INTO karr_environments (project_id, agent_id, name, image, gpu, env, mounts, command)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
RETURNING *;

-- name: UpdateEnvironmentStatus :exec
UPDATE karr_environments
SET status = $2, updated_at = now()
WHERE id = $1;

-- name: UpdateEnvironmentContainerID :exec
UPDATE karr_environments
SET container_id = $2, updated_at = now()
WHERE id = $1;

-- name: DeleteEnvironment :exec
DELETE FROM karr_environments WHERE id = $1;
