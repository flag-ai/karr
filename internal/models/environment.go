package models

import (
	"time"

	"github.com/google/uuid"
)

// EnvironmentStatus represents the lifecycle state of an environment.
type EnvironmentStatus string

// EnvironmentStatus constants.
const (
	EnvironmentStatusCreating EnvironmentStatus = "creating"
	EnvironmentStatusRunning  EnvironmentStatus = "running"
	EnvironmentStatusStopped  EnvironmentStatus = "stopped"
	EnvironmentStatusError    EnvironmentStatus = "error"
	EnvironmentStatusRemoved  EnvironmentStatus = "removed"
)

// Environment represents a container-based AI development environment.
type Environment struct {
	ID          uuid.UUID         `json:"id"`
	ProjectID   *uuid.UUID        `json:"project_id,omitempty"`
	AgentID     uuid.UUID         `json:"agent_id"`
	Name        string            `json:"name"`
	Image       string            `json:"image"`
	ContainerID string            `json:"container_id,omitempty"`
	Status      EnvironmentStatus `json:"status"`
	GPU         bool              `json:"gpu"`
	Env         []string          `json:"env,omitempty"`
	Mounts      []string          `json:"mounts,omitempty"`
	Command     []string          `json:"command,omitempty"`
	CreatedAt   time.Time         `json:"created_at"`
	UpdatedAt   time.Time         `json:"updated_at"`
}
