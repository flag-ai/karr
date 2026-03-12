// Package models defines the core domain types for KARR.
package models

import (
	"time"

	"github.com/google/uuid"
)

// AgentStatus represents the operational state of a BONNIE agent.
type AgentStatus string

// AgentStatus constants.
const (
	AgentStatusOnline  AgentStatus = "online"
	AgentStatusOffline AgentStatus = "offline"
	AgentStatusError   AgentStatus = "error"
)

// Agent represents a registered BONNIE GPU host agent.
type Agent struct {
	ID         uuid.UUID   `json:"id"`
	Name       string      `json:"name"`
	URL        string      `json:"url"`
	Token      string      `json:"-"`
	Status     AgentStatus `json:"status"`
	LastSeenAt *time.Time  `json:"last_seen_at,omitempty"`
	CreatedAt  time.Time   `json:"created_at"`
	UpdatedAt  time.Time   `json:"updated_at"`
}
