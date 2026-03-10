package service

import (
	"encoding/json"
	"fmt"
	"log/slog"
	"time"

	"github.com/flag-ai/karr/internal/db/sqlc"
	"github.com/flag-ai/karr/internal/models"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgtype"
)

// toPgUUID converts a google/uuid.UUID to a pgtype.UUID.
func toPgUUID(id uuid.UUID) pgtype.UUID {
	return pgtype.UUID{Bytes: [16]byte(id), Valid: true}
}

// fromPgUUID converts a pgtype.UUID to a google/uuid.UUID.
func fromPgUUID(id pgtype.UUID) uuid.UUID {
	return uuid.UUID(id.Bytes)
}

// timeFromPgTimestamptz converts a pgtype.Timestamptz to time.Time.
func timeFromPgTimestamptz(ts pgtype.Timestamptz) time.Time {
	if ts.Valid {
		return ts.Time
	}
	return time.Time{}
}

// timePtrFromPgTimestamptz converts a pgtype.Timestamptz to *time.Time.
// Returns nil if the timestamptz is not valid.
func timePtrFromPgTimestamptz(ts pgtype.Timestamptz) *time.Time {
	if ts.Valid {
		return &ts.Time
	}
	return nil
}

// agentFromRow converts a sqlc.KarrAgent to a models.Agent.
func agentFromRow(row sqlc.KarrAgent) models.Agent { //nolint:gocritic // value receiver for clean conversion API
	return models.Agent{
		ID:         fromPgUUID(row.ID),
		Name:       row.Name,
		URL:        row.Url,
		Token:      row.Token,
		Status:     models.AgentStatus(row.Status),
		LastSeenAt: timePtrFromPgTimestamptz(row.LastSeenAt),
		CreatedAt:  timeFromPgTimestamptz(row.CreatedAt),
		UpdatedAt:  timeFromPgTimestamptz(row.UpdatedAt),
	}
}

// projectFromRow converts a sqlc.KarrProject to a models.Project.
func projectFromRow(row sqlc.KarrProject) models.Project { //nolint:gocritic // value receiver for clean conversion API
	return models.Project{
		ID:          fromPgUUID(row.ID),
		Name:        row.Name,
		Description: row.Description,
		CreatedAt:   timeFromPgTimestamptz(row.CreatedAt),
		UpdatedAt:   timeFromPgTimestamptz(row.UpdatedAt),
	}
}

// environmentFromRow converts a sqlc.KarrEnvironment to a models.Environment.
func environmentFromRow(row sqlc.KarrEnvironment) models.Environment { //nolint:gocritic // value receiver for clean conversion API
	env := models.Environment{
		ID:          fromPgUUID(row.ID),
		AgentID:     fromPgUUID(row.AgentID),
		Name:        row.Name,
		Image:       row.Image,
		ContainerID: row.ContainerID,
		Status:      models.EnvironmentStatus(row.Status),
		GPU:         row.Gpu,
		CreatedAt:   timeFromPgTimestamptz(row.CreatedAt),
		UpdatedAt:   timeFromPgTimestamptz(row.UpdatedAt),
	}

	if row.ProjectID.Valid {
		pid := fromPgUUID(row.ProjectID)
		env.ProjectID = &pid
	}

	// Unmarshal JSONB fields — log warnings on corruption.
	if err := json.Unmarshal(row.Env, &env.Env); err != nil && len(row.Env) > 0 {
		slog.Warn("failed to unmarshal environment env field", "id", env.ID, "error", err)
	}
	if err := json.Unmarshal(row.Mounts, &env.Mounts); err != nil && len(row.Mounts) > 0 {
		slog.Warn("failed to unmarshal environment mounts field", "id", env.ID, "error", err)
	}
	if err := json.Unmarshal(row.Command, &env.Command); err != nil && len(row.Command) > 0 {
		slog.Warn("failed to unmarshal environment command field", "id", env.ID, "error", err)
	}

	return env
}

// marshalJSONB marshals v to JSON bytes suitable for a JSONB column.
// Returns an error if marshalling fails.
func marshalJSONB(v any) ([]byte, error) {
	if v == nil {
		return []byte("[]"), nil
	}
	b, err := json.Marshal(v)
	if err != nil {
		return nil, fmt.Errorf("marshal JSONB: %w", err)
	}
	return b, nil
}
