-- name: ListProjects :many
SELECT * FROM karr_projects ORDER BY name;

-- name: GetProject :one
SELECT * FROM karr_projects WHERE id = $1;

-- name: GetProjectByName :one
SELECT * FROM karr_projects WHERE name = $1;

-- name: CreateProject :one
INSERT INTO karr_projects (name, description)
VALUES ($1, $2)
RETURNING *;

-- name: UpdateProject :one
UPDATE karr_projects
SET name = $2, description = $3, updated_at = now()
WHERE id = $1
RETURNING *;

-- name: DeleteProject :exec
DELETE FROM karr_projects WHERE id = $1;
