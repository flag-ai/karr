package handlers

import (
	"context"
)

// AgentAvailabilityChecker checks whether at least one agent is online.
type AgentAvailabilityChecker interface {
	HasOnlineAgent(ctx context.Context) error
}

// BonnieChecker implements health.Checker to verify at least one
// BONNIE agent is reachable.
type BonnieChecker struct {
	agents AgentAvailabilityChecker
}

// NewBonnieChecker creates a health checker for BONNIE agent availability.
func NewBonnieChecker(agents AgentAvailabilityChecker) *BonnieChecker {
	return &BonnieChecker{agents: agents}
}

// Name returns the checker name.
func (c *BonnieChecker) Name() string {
	return "bonnie-agents"
}

// Check verifies at least one BONNIE agent is online.
func (c *BonnieChecker) Check(ctx context.Context) error {
	return c.agents.HasOnlineAgent(ctx)
}
