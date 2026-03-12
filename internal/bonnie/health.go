package bonnie

import (
	"context"
	"fmt"
)

// HasOnlineAgent reports whether at least one agent in the registry
// responded successfully to its most recent health check.
func (r *Registry) HasOnlineAgent(ctx context.Context) error {
	r.mu.RLock()
	count := len(r.agents)
	r.mu.RUnlock()

	if count == 0 {
		return fmt.Errorf("no agents registered")
	}

	// Check the database for at least one agent with status "online".
	agents, err := r.queries.ListAgents(ctx)
	if err != nil {
		return fmt.Errorf("query agents: %w", err)
	}

	for i := range agents {
		if agents[i].Status == "online" {
			return nil
		}
	}

	return fmt.Errorf("no online agents (%d registered, all offline)", count)
}
