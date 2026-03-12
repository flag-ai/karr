-- name: CreateAgentRegistration :one
INSERT INTO karr_agent_registrations (token_hash, label, status, expires_at)
VALUES ($1, $2, 'pending', now() + INTERVAL '1 hour')
RETURNING *;

-- name: GetPendingRegistration :one
SELECT * FROM karr_agent_registrations
WHERE token_hash = $1 AND status = 'pending' AND expires_at > now();

-- name: ClaimRegistration :exec
UPDATE karr_agent_registrations
SET status = 'claimed', agent_id = $2, claimed_at = now()
WHERE id = $1;

-- name: ListRegistrations :many
SELECT * FROM karr_agent_registrations
ORDER BY created_at DESC;

-- name: DeleteRegistration :exec
DELETE FROM karr_agent_registrations WHERE id = $1;

-- name: CleanExpiredRegistrations :exec
UPDATE karr_agent_registrations
SET status = 'expired'
WHERE status = 'pending' AND expires_at <= now();
