package service

import (
	"context"

	"github.com/flag-ai/karr/internal/models"
	"github.com/google/uuid"
)

// AgentServicer defines the handler-facing interface for agent operations.
type AgentServicer interface {
	List(ctx context.Context) ([]models.Agent, error)
	Get(ctx context.Context, id uuid.UUID) (models.Agent, error)
	Create(ctx context.Context, input CreateAgentInput) (models.Agent, error)
	Delete(ctx context.Context, id uuid.UUID) error
	GetStatus(ctx context.Context, id uuid.UUID) (AgentStatusResponse, error)
}

// ProjectServicer defines the handler-facing interface for project operations.
type ProjectServicer interface {
	List(ctx context.Context) ([]models.Project, error)
	Get(ctx context.Context, id uuid.UUID) (models.Project, error)
	Create(ctx context.Context, input CreateProjectInput) (models.Project, error)
	Update(ctx context.Context, id uuid.UUID, input UpdateProjectInput) (models.Project, error)
	Delete(ctx context.Context, id uuid.UUID) error
}

// EnvironmentServicer defines the handler-facing interface for environment operations.
type EnvironmentServicer interface {
	List(ctx context.Context) ([]models.Environment, error)
	Get(ctx context.Context, id uuid.UUID) (models.Environment, error)
	Create(ctx context.Context, input CreateEnvironmentInput) (models.Environment, error)
	Start(ctx context.Context, id uuid.UUID) error
	Stop(ctx context.Context, id uuid.UUID) error
	Remove(ctx context.Context, id uuid.UUID) error
	StreamLogs(ctx context.Context, id uuid.UUID, callback func(string)) error
}
