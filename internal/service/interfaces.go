package service

import (
	"context"

	"github.com/flag-ai/karr/internal/db/sqlc"
	"github.com/jackc/pgx/v5/pgtype"
)

// Querier defines the database operations used by services.
// This interface is satisfied by sqlc.Queries and can be mocked in tests.
type Querier interface {
	ListAgents(ctx context.Context) ([]sqlc.KarrAgent, error)
	GetAgent(ctx context.Context, id pgtype.UUID) (sqlc.KarrAgent, error)
	GetAgentByName(ctx context.Context, name string) (sqlc.KarrAgent, error)
	CreateAgent(ctx context.Context, arg sqlc.CreateAgentParams) (sqlc.KarrAgent, error)
	UpdateAgent(ctx context.Context, arg sqlc.UpdateAgentParams) (sqlc.KarrAgent, error)
	DeleteAgent(ctx context.Context, id pgtype.UUID) error
	UpdateAgentStatus(ctx context.Context, arg sqlc.UpdateAgentStatusParams) error

	ListProjects(ctx context.Context) ([]sqlc.KarrProject, error)
	GetProject(ctx context.Context, id pgtype.UUID) (sqlc.KarrProject, error)
	GetProjectByName(ctx context.Context, name string) (sqlc.KarrProject, error)
	CreateProject(ctx context.Context, arg sqlc.CreateProjectParams) (sqlc.KarrProject, error)
	UpdateProject(ctx context.Context, arg sqlc.UpdateProjectParams) (sqlc.KarrProject, error)
	DeleteProject(ctx context.Context, id pgtype.UUID) error

	ListEnvironments(ctx context.Context) ([]sqlc.KarrEnvironment, error)
	ListEnvironmentsByAgent(ctx context.Context, agentID pgtype.UUID) ([]sqlc.KarrEnvironment, error)
	ListEnvironmentsByProject(ctx context.Context, projectID pgtype.UUID) ([]sqlc.KarrEnvironment, error)
	GetEnvironment(ctx context.Context, id pgtype.UUID) (sqlc.KarrEnvironment, error)
	CreateEnvironment(ctx context.Context, arg sqlc.CreateEnvironmentParams) (sqlc.KarrEnvironment, error)
	UpdateEnvironmentStatus(ctx context.Context, arg sqlc.UpdateEnvironmentStatusParams) error
	UpdateEnvironmentContainerID(ctx context.Context, arg sqlc.UpdateEnvironmentContainerIDParams) error
	DeleteEnvironment(ctx context.Context, id pgtype.UUID) error
}
