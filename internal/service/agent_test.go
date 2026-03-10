package service

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"testing"

	"github.com/flag-ai/karr/internal/bonnie"
	"github.com/flag-ai/karr/internal/db/sqlc"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgtype"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// mockQuerier implements the Querier interface for testing.
type mockQuerier struct {
	agents       map[pgtype.UUID]sqlc.KarrAgent
	projects     map[pgtype.UUID]sqlc.KarrProject
	environments map[pgtype.UUID]sqlc.KarrEnvironment

	createAgentFn        func(ctx context.Context, arg sqlc.CreateAgentParams) (sqlc.KarrAgent, error)
	deleteAgentFn        func(ctx context.Context, id pgtype.UUID) error
	getAgentFn           func(ctx context.Context, id pgtype.UUID) (sqlc.KarrAgent, error)
	listAgentsFn         func(ctx context.Context) ([]sqlc.KarrAgent, error)
	createProjectFn      func(ctx context.Context, arg sqlc.CreateProjectParams) (sqlc.KarrProject, error)
	updateProjectFn      func(ctx context.Context, arg sqlc.UpdateProjectParams) (sqlc.KarrProject, error)
	getProjectFn         func(ctx context.Context, id pgtype.UUID) (sqlc.KarrProject, error)
	createEnvironmentFn  func(ctx context.Context, arg sqlc.CreateEnvironmentParams) (sqlc.KarrEnvironment, error)
	updateEnvStatusFn    func(ctx context.Context, arg sqlc.UpdateEnvironmentStatusParams) error
	updateEnvContainerFn func(ctx context.Context, arg sqlc.UpdateEnvironmentContainerIDParams) error
	getEnvironmentFn     func(ctx context.Context, id pgtype.UUID) (sqlc.KarrEnvironment, error)
	deleteEnvironmentFn  func(ctx context.Context, id pgtype.UUID) error
}

func newMockQuerier() *mockQuerier {
	return &mockQuerier{
		agents:       make(map[pgtype.UUID]sqlc.KarrAgent),
		projects:     make(map[pgtype.UUID]sqlc.KarrProject),
		environments: make(map[pgtype.UUID]sqlc.KarrEnvironment),
	}
}

func (m *mockQuerier) ListAgents(ctx context.Context) ([]sqlc.KarrAgent, error) {
	if m.listAgentsFn != nil {
		return m.listAgentsFn(ctx)
	}
	var result []sqlc.KarrAgent
	for _, a := range m.agents {
		result = append(result, a)
	}
	return result, nil
}

func (m *mockQuerier) GetAgent(ctx context.Context, id pgtype.UUID) (sqlc.KarrAgent, error) {
	if m.getAgentFn != nil {
		return m.getAgentFn(ctx, id)
	}
	a, ok := m.agents[id]
	if !ok {
		return sqlc.KarrAgent{}, fmt.Errorf("agent not found")
	}
	return a, nil
}

func (m *mockQuerier) GetAgentByName(ctx context.Context, name string) (sqlc.KarrAgent, error) {
	for _, a := range m.agents {
		if a.Name == name {
			return a, nil
		}
	}
	return sqlc.KarrAgent{}, fmt.Errorf("agent not found")
}

func (m *mockQuerier) CreateAgent(ctx context.Context, arg sqlc.CreateAgentParams) (sqlc.KarrAgent, error) {
	if m.createAgentFn != nil {
		return m.createAgentFn(ctx, arg)
	}
	id := uuid.New()
	pgID := toPgUUID(id)
	agent := sqlc.KarrAgent{
		ID:     pgID,
		Name:   arg.Name,
		Url:    arg.Url,
		Token:  arg.Token,
		Status: arg.Status,
	}
	m.agents[pgID] = agent
	return agent, nil
}

func (m *mockQuerier) UpdateAgent(ctx context.Context, arg sqlc.UpdateAgentParams) (sqlc.KarrAgent, error) {
	a, ok := m.agents[arg.ID]
	if !ok {
		return sqlc.KarrAgent{}, fmt.Errorf("agent not found")
	}
	a.Name = arg.Name
	a.Url = arg.Url
	a.Token = arg.Token
	m.agents[arg.ID] = a
	return a, nil
}

func (m *mockQuerier) DeleteAgent(ctx context.Context, id pgtype.UUID) error {
	if m.deleteAgentFn != nil {
		return m.deleteAgentFn(ctx, id)
	}
	delete(m.agents, id)
	return nil
}

func (m *mockQuerier) UpdateAgentStatus(ctx context.Context, arg sqlc.UpdateAgentStatusParams) error {
	a, ok := m.agents[arg.ID]
	if !ok {
		return fmt.Errorf("agent not found")
	}
	a.Status = arg.Status
	m.agents[arg.ID] = a
	return nil
}

func (m *mockQuerier) ListProjects(ctx context.Context) ([]sqlc.KarrProject, error) {
	var result []sqlc.KarrProject
	for _, p := range m.projects {
		result = append(result, p)
	}
	return result, nil
}

func (m *mockQuerier) GetProject(ctx context.Context, id pgtype.UUID) (sqlc.KarrProject, error) {
	if m.getProjectFn != nil {
		return m.getProjectFn(ctx, id)
	}
	p, ok := m.projects[id]
	if !ok {
		return sqlc.KarrProject{}, fmt.Errorf("project not found")
	}
	return p, nil
}

func (m *mockQuerier) GetProjectByName(ctx context.Context, name string) (sqlc.KarrProject, error) {
	for _, p := range m.projects {
		if p.Name == name {
			return p, nil
		}
	}
	return sqlc.KarrProject{}, fmt.Errorf("project not found")
}

func (m *mockQuerier) CreateProject(ctx context.Context, arg sqlc.CreateProjectParams) (sqlc.KarrProject, error) {
	if m.createProjectFn != nil {
		return m.createProjectFn(ctx, arg)
	}
	id := uuid.New()
	pgID := toPgUUID(id)
	proj := sqlc.KarrProject{
		ID:          pgID,
		Name:        arg.Name,
		Description: arg.Description,
	}
	m.projects[pgID] = proj
	return proj, nil
}

func (m *mockQuerier) UpdateProject(ctx context.Context, arg sqlc.UpdateProjectParams) (sqlc.KarrProject, error) {
	if m.updateProjectFn != nil {
		return m.updateProjectFn(ctx, arg)
	}
	p, ok := m.projects[arg.ID]
	if !ok {
		return sqlc.KarrProject{}, fmt.Errorf("project not found")
	}
	p.Name = arg.Name
	p.Description = arg.Description
	m.projects[arg.ID] = p
	return p, nil
}

func (m *mockQuerier) DeleteProject(ctx context.Context, id pgtype.UUID) error {
	delete(m.projects, id)
	return nil
}

func (m *mockQuerier) ListEnvironments(ctx context.Context) ([]sqlc.KarrEnvironment, error) {
	var result []sqlc.KarrEnvironment
	for _, e := range m.environments {
		result = append(result, e)
	}
	return result, nil
}

func (m *mockQuerier) ListEnvironmentsByAgent(ctx context.Context, agentID pgtype.UUID) ([]sqlc.KarrEnvironment, error) {
	var result []sqlc.KarrEnvironment
	for _, e := range m.environments {
		if e.AgentID == agentID {
			result = append(result, e)
		}
	}
	return result, nil
}

func (m *mockQuerier) ListEnvironmentsByProject(ctx context.Context, projectID pgtype.UUID) ([]sqlc.KarrEnvironment, error) {
	var result []sqlc.KarrEnvironment
	for _, e := range m.environments {
		if e.ProjectID == projectID {
			result = append(result, e)
		}
	}
	return result, nil
}

func (m *mockQuerier) GetEnvironment(ctx context.Context, id pgtype.UUID) (sqlc.KarrEnvironment, error) {
	if m.getEnvironmentFn != nil {
		return m.getEnvironmentFn(ctx, id)
	}
	e, ok := m.environments[id]
	if !ok {
		return sqlc.KarrEnvironment{}, fmt.Errorf("environment not found")
	}
	return e, nil
}

func (m *mockQuerier) CreateEnvironment(ctx context.Context, arg sqlc.CreateEnvironmentParams) (sqlc.KarrEnvironment, error) {
	if m.createEnvironmentFn != nil {
		return m.createEnvironmentFn(ctx, arg)
	}
	id := uuid.New()
	pgID := toPgUUID(id)
	env := sqlc.KarrEnvironment{
		ID:        pgID,
		ProjectID: arg.ProjectID,
		AgentID:   arg.AgentID,
		Name:      arg.Name,
		Image:     arg.Image,
		Status:    "creating",
		Gpu:       arg.Gpu,
		Env:       arg.Env,
		Mounts:    arg.Mounts,
		Command:   arg.Command,
	}
	m.environments[pgID] = env
	return env, nil
}

func (m *mockQuerier) UpdateEnvironmentStatus(ctx context.Context, arg sqlc.UpdateEnvironmentStatusParams) error {
	if m.updateEnvStatusFn != nil {
		return m.updateEnvStatusFn(ctx, arg)
	}
	e, ok := m.environments[arg.ID]
	if !ok {
		return fmt.Errorf("environment not found")
	}
	e.Status = arg.Status
	m.environments[arg.ID] = e
	return nil
}

func (m *mockQuerier) UpdateEnvironmentContainerID(ctx context.Context, arg sqlc.UpdateEnvironmentContainerIDParams) error {
	if m.updateEnvContainerFn != nil {
		return m.updateEnvContainerFn(ctx, arg)
	}
	e, ok := m.environments[arg.ID]
	if !ok {
		return fmt.Errorf("environment not found")
	}
	e.ContainerID = arg.ContainerID
	m.environments[arg.ID] = e
	return nil
}

func (m *mockQuerier) DeleteEnvironment(ctx context.Context, id pgtype.UUID) error {
	if m.deleteEnvironmentFn != nil {
		return m.deleteEnvironmentFn(ctx, id)
	}
	delete(m.environments, id)
	return nil
}

// mockBonnieClient implements bonnie.Client for testing.
type mockBonnieClient struct {
	systemInfoFn      func(ctx context.Context) (*bonnie.SystemInfoResponse, error)
	gpuStatusFn       func(ctx context.Context) (*bonnie.GPUSnapshot, error)
	createContainerFn func(ctx context.Context, req *bonnie.CreateContainerRequest) (string, error)
	startContainerFn  func(ctx context.Context, id string) error
	stopContainerFn   func(ctx context.Context, id string) error
	removeContainerFn func(ctx context.Context, id string) error
	streamLogsFn      func(ctx context.Context, id string, callback func(data string)) error
}

func (c *mockBonnieClient) SystemInfo(ctx context.Context) (*bonnie.SystemInfoResponse, error) {
	if c.systemInfoFn != nil {
		return c.systemInfoFn(ctx)
	}
	return &bonnie.SystemInfoResponse{}, nil
}

func (c *mockBonnieClient) GPUStatus(ctx context.Context) (*bonnie.GPUSnapshot, error) {
	if c.gpuStatusFn != nil {
		return c.gpuStatusFn(ctx)
	}
	return &bonnie.GPUSnapshot{}, nil
}

func (c *mockBonnieClient) ListContainers(ctx context.Context) ([]bonnie.ContainerInfo, error) {
	return nil, nil
}

func (c *mockBonnieClient) CreateContainer(ctx context.Context, req *bonnie.CreateContainerRequest) (string, error) {
	if c.createContainerFn != nil {
		return c.createContainerFn(ctx, req)
	}
	return "container-123", nil
}

func (c *mockBonnieClient) StartContainer(ctx context.Context, id string) error {
	if c.startContainerFn != nil {
		return c.startContainerFn(ctx, id)
	}
	return nil
}

func (c *mockBonnieClient) StopContainer(ctx context.Context, id string) error {
	if c.stopContainerFn != nil {
		return c.stopContainerFn(ctx, id)
	}
	return nil
}

func (c *mockBonnieClient) RestartContainer(ctx context.Context, id string) error {
	return nil
}

func (c *mockBonnieClient) RemoveContainer(ctx context.Context, id string) error {
	if c.removeContainerFn != nil {
		return c.removeContainerFn(ctx, id)
	}
	return nil
}

func (c *mockBonnieClient) StreamLogs(ctx context.Context, id string, callback func(data string)) error {
	if c.streamLogsFn != nil {
		return c.streamLogsFn(ctx, id, callback)
	}
	return nil
}

func (c *mockBonnieClient) Health(ctx context.Context) error {
	return nil
}

func testLogger() *slog.Logger {
	return slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelError}))
}

// Compile-time interface checks for mocks.
var _ Querier = (*mockQuerier)(nil)
var _ bonnie.Client = (*mockBonnieClient)(nil)

// --- Agent Service Tests ---

func TestAgentService_Create(t *testing.T) {
	mq := newMockQuerier()
	reg := bonnie.NewRegistry(nil, testLogger())
	svc := NewAgentService(mq, reg, testLogger())
	ctx := context.Background()

	agent, err := svc.Create(ctx, CreateAgentInput{
		Name:  "gpu-host-1",
		URL:   "https://gpu1.example.com",
		Token: "secret-token",
	})

	require.NoError(t, err)
	assert.Equal(t, "gpu-host-1", agent.Name)
	assert.Equal(t, "https://gpu1.example.com", agent.URL)
	assert.Empty(t, agent.Token, "token should be stripped from response")
	assert.NotEqual(t, uuid.Nil, agent.ID)

	// Agent should be in the registry.
	_, ok := reg.Get(agent.ID)
	assert.True(t, ok, "agent should be registered in the BONNIE registry")
}

func TestAgentService_Create_ValidationError(t *testing.T) {
	mq := newMockQuerier()
	reg := bonnie.NewRegistry(nil, testLogger())
	svc := NewAgentService(mq, reg, testLogger())
	ctx := context.Background()

	// Empty name.
	_, err := svc.Create(ctx, CreateAgentInput{
		Name: "",
		URL:  "https://gpu1.example.com",
	})
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "name is required")

	// Empty URL.
	_, err = svc.Create(ctx, CreateAgentInput{
		Name: "test",
		URL:  "",
	})
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "url is required")
}

func TestAgentService_Delete(t *testing.T) {
	mq := newMockQuerier()
	reg := bonnie.NewRegistry(nil, testLogger())
	svc := NewAgentService(mq, reg, testLogger())
	ctx := context.Background()

	// Create an agent first.
	agent, err := svc.Create(ctx, CreateAgentInput{
		Name:  "gpu-host-1",
		URL:   "https://gpu1.example.com",
		Token: "secret",
	})
	require.NoError(t, err)

	// Delete it.
	err = svc.Delete(ctx, agent.ID)
	require.NoError(t, err)

	// Should be gone from registry.
	_, ok := reg.Get(agent.ID)
	assert.False(t, ok, "agent should be unregistered after deletion")
}

func TestAgentService_GetStatus_NoClient(t *testing.T) {
	mq := newMockQuerier()
	reg := bonnie.NewRegistry(nil, testLogger())
	svc := NewAgentService(mq, reg, testLogger())
	ctx := context.Background()

	// Create an agent, then unregister it to simulate missing BONNIE client.
	agent, err := svc.Create(ctx, CreateAgentInput{
		Name:  "gpu-host-1",
		URL:   "https://gpu1.example.com",
		Token: "secret",
	})
	require.NoError(t, err)
	reg.Unregister(agent.ID)

	// GetStatus should return agent info without system/gpu data.
	status, err := svc.GetStatus(ctx, agent.ID)
	require.NoError(t, err)
	assert.Equal(t, agent.ID, status.Agent.ID)
	assert.Nil(t, status.System)
	assert.Nil(t, status.GPU)
}

func TestAgentService_List(t *testing.T) {
	mq := newMockQuerier()
	reg := bonnie.NewRegistry(nil, testLogger())
	svc := NewAgentService(mq, reg, testLogger())
	ctx := context.Background()

	_, err := svc.Create(ctx, CreateAgentInput{
		Name:  "agent-1",
		URL:   "https://agent1.example.com",
		Token: "token-1",
	})
	require.NoError(t, err)

	_, err = svc.Create(ctx, CreateAgentInput{
		Name:  "agent-2",
		URL:   "https://agent2.example.com",
		Token: "token-2",
	})
	require.NoError(t, err)

	agents, err := svc.List(ctx)
	require.NoError(t, err)
	assert.Len(t, agents, 2)

	// Tokens should be stripped.
	for _, a := range agents {
		assert.Empty(t, a.Token)
	}
}

func TestAgentService_Get(t *testing.T) {
	mq := newMockQuerier()
	reg := bonnie.NewRegistry(nil, testLogger())
	svc := NewAgentService(mq, reg, testLogger())
	ctx := context.Background()

	created, err := svc.Create(ctx, CreateAgentInput{
		Name:  "gpu-host-1",
		URL:   "https://gpu1.example.com",
		Token: "secret",
	})
	require.NoError(t, err)

	agent, err := svc.Get(ctx, created.ID)
	require.NoError(t, err)
	assert.Equal(t, created.ID, agent.ID)
	assert.Equal(t, "gpu-host-1", agent.Name)
	assert.Empty(t, agent.Token, "token should be stripped")
}
