package bonnie

import (
	"context"
	"fmt"
	"log/slog"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgtype"

	"github.com/flag-ai/karr/internal/db/sqlc"
)

// agentEntry holds a BONNIE client and its database identity.
type agentEntry struct {
	ID     uuid.UUID
	Name   string
	URL    string
	Token  string
	Client Client
}

// Registry manages connections to multiple BONNIE agents.
type Registry struct {
	mu      sync.RWMutex
	agents  map[uuid.UUID]*agentEntry
	queries *sqlc.Queries
	logger  *slog.Logger
}

// NewRegistry creates an agent registry.
func NewRegistry(queries *sqlc.Queries, logger *slog.Logger) *Registry {
	return &Registry{
		agents:  make(map[uuid.UUID]*agentEntry),
		queries: queries,
		logger:  logger,
	}
}

// Register adds an agent to the registry.
func (r *Registry) Register(id uuid.UUID, name, url, token string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.agents[id] = &agentEntry{
		ID:     id,
		Name:   name,
		URL:    url,
		Token:  token,
		Client: NewClient(url, token),
	}
}

// Unregister removes an agent from the registry.
func (r *Registry) Unregister(id uuid.UUID) {
	r.mu.Lock()
	defer r.mu.Unlock()
	delete(r.agents, id)
}

// Get returns the BONNIE client for an agent.
func (r *Registry) Get(id uuid.UUID) (Client, bool) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	entry, ok := r.agents[id]
	if !ok {
		return nil, false
	}
	return entry.Client, true
}

// LoadFromDB loads all agents from the database into the registry.
func (r *Registry) LoadFromDB(ctx context.Context) error {
	agents, err := r.queries.ListAgents(ctx)
	if err != nil {
		return fmt.Errorf("registry: load agents: %w", err)
	}
	for i := range agents {
		id, err := uuid.FromBytes(agents[i].ID.Bytes[:])
		if err != nil {
			continue
		}
		r.Register(id, agents[i].Name, agents[i].Url, agents[i].Token)
	}
	r.logger.Info("loaded agents from database", "count", len(agents))
	return nil
}

// EnsureDefault registers the default agent if it doesn't already exist.
func (r *Registry) EnsureDefault(ctx context.Context, url, token string) error {
	// Check if an agent with this URL already exists.
	agents, err := r.queries.ListAgents(ctx)
	if err != nil {
		return err
	}
	for i := range agents {
		if agents[i].Url == url {
			return nil // Already registered.
		}
	}

	agent, err := r.queries.CreateAgent(ctx, sqlc.CreateAgentParams{
		Name:   "default",
		Url:    url,
		Token:  token,
		Status: "offline",
	})
	if err != nil {
		return fmt.Errorf("registry: create default agent: %w", err)
	}

	id, _ := uuid.FromBytes(agent.ID.Bytes[:])
	r.Register(id, agent.Name, agent.Url, agent.Token)
	r.logger.Info("registered default agent", "url", url)
	return nil
}

// StartHealthLoop pings all agents every 30s and updates their status in the DB.
func (r *Registry) StartHealthLoop(ctx context.Context) {
	go func() {
		ticker := time.NewTicker(30 * time.Second)
		defer ticker.Stop()

		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				r.checkAll(ctx)
			}
		}
	}()
}

func (r *Registry) checkAll(ctx context.Context) {
	r.mu.RLock()
	entries := make([]*agentEntry, 0, len(r.agents))
	for _, e := range r.agents {
		entries = append(entries, e)
	}
	r.mu.RUnlock()

	for _, entry := range entries {
		status := "online"
		err := entry.Client.Health(ctx)
		if err != nil {
			status = "offline"
			r.logger.Debug("agent health check failed", "agent", entry.Name, "error", err)
		}

		now := time.Now()
		pgID := pgtype.UUID{Bytes: uuidToBytes(entry.ID), Valid: true}
		pgTime := pgtype.Timestamptz{Time: now, Valid: true}

		if updateErr := r.queries.UpdateAgentStatus(ctx, sqlc.UpdateAgentStatusParams{
			ID:         pgID,
			Status:     status,
			LastSeenAt: pgTime,
		}); updateErr != nil {
			r.logger.Error("failed to update agent status", "agent", entry.Name, "error", updateErr)
		}
	}
}

func uuidToBytes(id uuid.UUID) [16]byte {
	return [16]byte(id)
}
