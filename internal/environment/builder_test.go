package environment

import (
	"context"
	"fmt"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgtype"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/flag-ai/karr/internal/db/sqlc"
)

// testPgUUID creates a random pgtype.UUID for testing.
func testPgUUID() pgtype.UUID {
	id := uuid.New()
	return pgtype.UUID{Bytes: [16]byte(id), Valid: true}
}

// mockQuerier implements the Querier interface for testing.
type mockQuerier struct {
	agents   map[string]sqlc.KarrAgent
	projects map[string]sqlc.KarrProject
}

func (m *mockQuerier) GetAgentByName(_ context.Context, name string) (sqlc.KarrAgent, error) {
	agent, ok := m.agents[name]
	if !ok {
		return sqlc.KarrAgent{}, fmt.Errorf("agent not found: %s", name)
	}
	return agent, nil
}

func (m *mockQuerier) GetProjectByName(_ context.Context, name string) (sqlc.KarrProject, error) {
	project, ok := m.projects[name]
	if !ok {
		return sqlc.KarrProject{}, fmt.Errorf("project not found: %s", name)
	}
	return project, nil
}

func TestBuild_AgentOnly(t *testing.T) {
	agentUUID := testPgUUID()

	q := &mockQuerier{
		agents: map[string]sqlc.KarrAgent{
			"agent-1": {ID: agentUUID, Name: "agent-1"},
		},
	}

	builder := NewBuilder(q)
	spec := &Spec{
		Name:  "test-env",
		Agent: "agent-1",
		Image: "ubuntu:22.04",
		GPU:   true,
		Env:   []string{"FOO=bar"},
	}

	input, err := builder.Build(context.Background(), spec)
	require.NoError(t, err)

	assert.Equal(t, uuid.UUID(agentUUID.Bytes), input.AgentID)
	assert.Nil(t, input.ProjectID)
	assert.Equal(t, "test-env", input.Name)
	assert.Equal(t, "ubuntu:22.04", input.Image)
	assert.True(t, input.GPU)
	assert.Equal(t, []string{"FOO=bar"}, input.Env)
}

func TestBuild_AgentAndProject(t *testing.T) {
	agentUUID := testPgUUID()
	projectUUID := testPgUUID()

	q := &mockQuerier{
		agents: map[string]sqlc.KarrAgent{
			"agent-1": {ID: agentUUID, Name: "agent-1"},
		},
		projects: map[string]sqlc.KarrProject{
			"my-project": {ID: projectUUID, Name: "my-project"},
		},
	}

	builder := NewBuilder(q)
	spec := &Spec{
		Name:    "test-env",
		Agent:   "agent-1",
		Project: "my-project",
		Image:   "ubuntu:22.04",
	}

	input, err := builder.Build(context.Background(), spec)
	require.NoError(t, err)

	assert.Equal(t, uuid.UUID(agentUUID.Bytes), input.AgentID)
	require.NotNil(t, input.ProjectID)
	assert.Equal(t, uuid.UUID(projectUUID.Bytes), *input.ProjectID)
	assert.Equal(t, "test-env", input.Name)
}

func TestBuild_AgentNotFound(t *testing.T) {
	q := &mockQuerier{
		agents: map[string]sqlc.KarrAgent{},
	}

	builder := NewBuilder(q)
	spec := &Spec{
		Name:  "test-env",
		Agent: "missing-agent",
		Image: "ubuntu:22.04",
	}

	_, err := builder.Build(context.Background(), spec)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "resolve agent")
	assert.Contains(t, err.Error(), "missing-agent")
}

func TestBuild_ProjectNotFound(t *testing.T) {
	agentUUID := testPgUUID()

	q := &mockQuerier{
		agents: map[string]sqlc.KarrAgent{
			"agent-1": {ID: agentUUID, Name: "agent-1"},
		},
		projects: map[string]sqlc.KarrProject{},
	}

	builder := NewBuilder(q)
	spec := &Spec{
		Name:    "test-env",
		Agent:   "agent-1",
		Project: "missing-project",
		Image:   "ubuntu:22.04",
	}

	_, err := builder.Build(context.Background(), spec)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "resolve project")
	assert.Contains(t, err.Error(), "missing-project")
}
