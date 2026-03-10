package environment

import (
	"context"
	"fmt"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgtype"

	"github.com/flag-ai/karr/internal/db/sqlc"
	"github.com/flag-ai/karr/internal/service"
)

// Querier is the subset of sqlc.Queries used by Builder.
type Querier interface {
	GetAgentByName(ctx context.Context, name string) (sqlc.KarrAgent, error)
	GetProjectByName(ctx context.Context, name string) (sqlc.KarrProject, error)
}

// Builder resolves a Spec into a CreateEnvironmentInput by looking up agent
// and project names in the database.
type Builder struct {
	queries Querier
}

// NewBuilder creates a Builder.
func NewBuilder(queries Querier) *Builder {
	return &Builder{queries: queries}
}

// Build resolves the spec into a CreateEnvironmentInput.
func (b *Builder) Build(ctx context.Context, spec *Spec) (service.CreateEnvironmentInput, error) {
	// Resolve agent name to ID.
	agent, err := b.queries.GetAgentByName(ctx, spec.Agent)
	if err != nil {
		return service.CreateEnvironmentInput{}, fmt.Errorf("resolve agent %q: %w", spec.Agent, err)
	}
	agentID := pgUUIDToUUID(agent.ID)

	input := service.CreateEnvironmentInput{
		AgentID: agentID,
		Name:    spec.Name,
		Image:   spec.Image,
		GPU:     spec.GPU,
		Env:     spec.Env,
		Mounts:  spec.Mounts,
		Command: spec.Command,
	}

	// Resolve optional project name to ID.
	if spec.Project != "" {
		project, err := b.queries.GetProjectByName(ctx, spec.Project)
		if err != nil {
			return service.CreateEnvironmentInput{}, fmt.Errorf("resolve project %q: %w", spec.Project, err)
		}
		projectID := pgUUIDToUUID(project.ID)
		input.ProjectID = &projectID
	}

	return input, nil
}

// pgUUIDToUUID converts a pgtype.UUID to a google/uuid.UUID.
func pgUUIDToUUID(id pgtype.UUID) uuid.UUID {
	return uuid.UUID(id.Bytes)
}
