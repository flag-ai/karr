package service

import (
	"context"
	"time"

	"github.com/flag-ai/commons/bonnie"

	"github.com/flag-ai/karr/internal/db/sqlc"
)

// bonnieStore adapts KARR's sqlc queries to the bonnie.RegistryStore
// contract so the shared registry can persist agent state without
// knowing the database schema.
type bonnieStore struct {
	queries *sqlc.Queries
}

// NewBonnieRegistryStore returns a bonnie.RegistryStore backed by the
// karr_agents table.
func NewBonnieRegistryStore(q *sqlc.Queries) bonnie.RegistryStore {
	return &bonnieStore{queries: q}
}

// List returns every agent known to the database.
func (s *bonnieStore) List(ctx context.Context) ([]bonnie.Agent, error) {
	rows, err := s.queries.ListAgents(ctx)
	if err != nil {
		return nil, err
	}
	out := make([]bonnie.Agent, 0, len(rows))
	for i := range rows {
		r := rows[i]
		out = append(out, bonnie.Agent{
			ID:         fromPgUUID(r.ID).String(),
			Name:       r.Name,
			URL:        r.Url,
			Token:      r.Token,
			Status:     r.Status,
			LastSeenAt: timeFromPgTimestamptz(r.LastSeenAt),
		})
	}
	return out, nil
}

// UpdateStatus writes the latest health-check result back to the
// database. Unknown id strings are returned as errors from the query.
func (s *bonnieStore) UpdateStatus(ctx context.Context, id, status string, lastSeenAt time.Time) error {
	uid, err := parseUUIDString(id)
	if err != nil {
		return err
	}
	return s.queries.UpdateAgentStatus(ctx, sqlc.UpdateAgentStatusParams{
		ID:         toPgUUID(uid),
		Status:     status,
		LastSeenAt: pgTimestamptz(lastSeenAt),
	})
}
