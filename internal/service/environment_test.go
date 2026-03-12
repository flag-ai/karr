package service

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/flag-ai/karr/internal/bonnie"
	"github.com/flag-ai/karr/internal/db/sqlc"
	"github.com/google/uuid"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// newFakeBonnieServer returns an httptest.Server that fakes the BONNIE API
// endpoints needed by the environment service Create flow.
func newFakeBonnieServer() *httptest.Server {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/containers", func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodPost {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusCreated)
			_ = json.NewEncoder(w).Encode(map[string]string{"id": "fake-container-id"})
			return
		}
		w.WriteHeader(http.StatusMethodNotAllowed)
	})
	mux.HandleFunc("/", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
	return httptest.NewServer(mux)
}

// testEnvSetup creates a mock querier, registry (backed by a fake BONNIE
// server), environment service, and a pre-registered agent.
type testEnvSetup struct {
	mq      *mockQuerier
	reg     *bonnie.Registry
	svc     *EnvironmentService
	agentID uuid.UUID
	server  *httptest.Server
}

func newTestEnvSetup(t *testing.T) *testEnvSetup {
	t.Helper()

	server := newFakeBonnieServer()
	t.Cleanup(server.Close)

	mq := newMockQuerier()
	reg := bonnie.NewRegistry(nil, testLogger())
	svc := NewEnvironmentService(mq, reg, testLogger())

	// Register a fake agent whose URL points to our httptest server.
	agentID := uuid.New()
	pgAgentID := toPgUUID(agentID)
	mq.agents[pgAgentID] = sqlc.KarrAgent{
		ID:     pgAgentID,
		Name:   "test-agent",
		Url:    server.URL,
		Token:  "token",
		Status: "online",
	}
	reg.Register(agentID, "test-agent", server.URL, "token")

	return &testEnvSetup{
		mq:      mq,
		reg:     reg,
		svc:     svc,
		agentID: agentID,
		server:  server,
	}
}

func TestEnvironmentService_Create_Success(t *testing.T) {
	s := newTestEnvSetup(t)
	ctx := context.Background()

	env, err := s.svc.Create(ctx, CreateEnvironmentInput{
		AgentID: s.agentID,
		Name:    "dev-env",
		Image:   "nvidia/cuda:12.0",
		GPU:     true,
		Env:     []string{"CUDA_VISIBLE_DEVICES=0"},
		Mounts:  []string{"/data:/data"},
		Command: []string{"bash"},
	})

	require.NoError(t, err)
	assert.Equal(t, "dev-env", env.Name)
	assert.Equal(t, "nvidia/cuda:12.0", env.Image)
	assert.True(t, env.GPU)
	assert.Equal(t, "stopped", string(env.Status))
	assert.Equal(t, "fake-container-id", env.ContainerID)
}

func TestEnvironmentService_Create_ValidationError(t *testing.T) {
	s := newTestEnvSetup(t)
	ctx := context.Background()

	// Empty name.
	_, err := s.svc.Create(ctx, CreateEnvironmentInput{
		AgentID: s.agentID,
		Name:    "",
		Image:   "ubuntu:latest",
	})
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "name is required")

	// Empty image.
	_, err = s.svc.Create(ctx, CreateEnvironmentInput{
		AgentID: s.agentID,
		Name:    "test",
		Image:   "",
	})
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "image is required")
}

func TestEnvironmentService_Create_NoClient(t *testing.T) {
	s := newTestEnvSetup(t)
	ctx := context.Background()

	// Unregister the agent so there's no BONNIE client.
	s.reg.Unregister(s.agentID)

	_, err := s.svc.Create(ctx, CreateEnvironmentInput{
		AgentID: s.agentID,
		Name:    "dev-env",
		Image:   "ubuntu:latest",
	})
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "no BONNIE client")

	// The environment should have been created in DB but marked as error.
	var found bool
	for _, e := range s.mq.environments {
		if e.Name == "dev-env" {
			found = true
			assert.Equal(t, "error", e.Status)
		}
	}
	assert.True(t, found, "environment should exist in DB with error status")
}

func TestEnvironmentService_Create_ContainerFails(t *testing.T) {
	// Create a server that returns an error for container creation.
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer server.Close()

	mq := newMockQuerier()
	reg := bonnie.NewRegistry(nil, testLogger())
	svc := NewEnvironmentService(mq, reg, testLogger())
	ctx := context.Background()

	agentID := uuid.New()
	pgAgentID := toPgUUID(agentID)
	mq.agents[pgAgentID] = sqlc.KarrAgent{
		ID:     pgAgentID,
		Name:   "test-agent",
		Url:    server.URL,
		Status: "online",
	}
	reg.Register(agentID, "test-agent", server.URL, "token")

	_, err := svc.Create(ctx, CreateEnvironmentInput{
		AgentID: agentID,
		Name:    "will-fail",
		Image:   "ubuntu:latest",
	})
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "create container")

	// Environment should be marked as error in DB.
	for _, e := range mq.environments {
		if e.Name == "will-fail" {
			assert.Equal(t, "error", e.Status)
		}
	}
}

func TestEnvironmentService_List(t *testing.T) {
	s := newTestEnvSetup(t)
	ctx := context.Background()

	_, err := s.svc.Create(ctx, CreateEnvironmentInput{
		AgentID: s.agentID,
		Name:    "env-1",
		Image:   "ubuntu:latest",
	})
	require.NoError(t, err)

	_, err = s.svc.Create(ctx, CreateEnvironmentInput{
		AgentID: s.agentID,
		Name:    "env-2",
		Image:   "ubuntu:latest",
	})
	require.NoError(t, err)

	envs, err := s.svc.List(ctx)
	require.NoError(t, err)
	assert.Len(t, envs, 2)
}

func TestEnvironmentService_ListByAgent(t *testing.T) {
	s := newTestEnvSetup(t)
	ctx := context.Background()

	_, err := s.svc.Create(ctx, CreateEnvironmentInput{
		AgentID: s.agentID,
		Name:    "env-1",
		Image:   "ubuntu:latest",
	})
	require.NoError(t, err)

	envs, err := s.svc.ListByAgent(ctx, s.agentID)
	require.NoError(t, err)
	assert.Len(t, envs, 1)

	// Different agent should return empty.
	envs, err = s.svc.ListByAgent(ctx, uuid.New())
	require.NoError(t, err)
	assert.Empty(t, envs)
}

func TestEnvironmentService_ListByProject(t *testing.T) {
	s := newTestEnvSetup(t)
	ctx := context.Background()

	projectID := uuid.New()
	_, err := s.svc.Create(ctx, CreateEnvironmentInput{
		ProjectID: &projectID,
		AgentID:   s.agentID,
		Name:      "env-in-project",
		Image:     "ubuntu:latest",
	})
	require.NoError(t, err)

	envs, err := s.svc.ListByProject(ctx, projectID)
	require.NoError(t, err)
	assert.Len(t, envs, 1)
	assert.Equal(t, &projectID, envs[0].ProjectID)
}

func TestEnvironmentService_Get(t *testing.T) {
	s := newTestEnvSetup(t)
	ctx := context.Background()

	created, err := s.svc.Create(ctx, CreateEnvironmentInput{
		AgentID: s.agentID,
		Name:    "dev-env",
		Image:   "ubuntu:latest",
	})
	require.NoError(t, err)

	env, err := s.svc.Get(ctx, created.ID)
	require.NoError(t, err)
	assert.Equal(t, created.ID, env.ID)
	assert.Equal(t, "dev-env", env.Name)
}

func TestEnvironmentService_Get_NotFound(t *testing.T) {
	s := newTestEnvSetup(t)
	ctx := context.Background()

	_, err := s.svc.Get(ctx, uuid.New())
	assert.Error(t, err)
}

func TestEnvironmentService_Remove_NoContainer(t *testing.T) {
	mq := newMockQuerier()
	reg := bonnie.NewRegistry(nil, testLogger())
	svc := NewEnvironmentService(mq, reg, testLogger())
	ctx := context.Background()

	// Manually add an environment with no container ID.
	agentID := uuid.New()
	envID := uuid.New()
	pgEnvID := toPgUUID(envID)
	pgAgentID := toPgUUID(agentID)

	server := newFakeBonnieServer()
	defer server.Close()

	mq.environments[pgEnvID] = sqlc.KarrEnvironment{
		ID:          pgEnvID,
		AgentID:     pgAgentID,
		Name:        "orphan-env",
		Image:       "ubuntu:latest",
		ContainerID: "",
		Status:      "error",
	}
	reg.Register(agentID, "test-agent", server.URL, "token")

	err := svc.Remove(ctx, envID)
	require.NoError(t, err)

	// Should be deleted from DB.
	_, ok := mq.environments[pgEnvID]
	assert.False(t, ok, "environment should be deleted from DB")
}

func TestEnvironmentService_StreamLogs_NoContainer(t *testing.T) {
	mq := newMockQuerier()
	reg := bonnie.NewRegistry(nil, testLogger())
	svc := NewEnvironmentService(mq, reg, testLogger())
	ctx := context.Background()

	agentID := uuid.New()
	envID := uuid.New()
	pgEnvID := toPgUUID(envID)
	pgAgentID := toPgUUID(agentID)

	server := newFakeBonnieServer()
	defer server.Close()

	mq.environments[pgEnvID] = sqlc.KarrEnvironment{
		ID:          pgEnvID,
		AgentID:     pgAgentID,
		Name:        "no-container",
		Image:       "ubuntu:latest",
		ContainerID: "",
		Status:      "error",
	}
	reg.Register(agentID, "test-agent", server.URL, "token")

	err := svc.StreamLogs(ctx, envID, func(data string) {})
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "has no container")
}

func TestEnvironmentService_Start_NoClient(t *testing.T) {
	mq := newMockQuerier()
	reg := bonnie.NewRegistry(nil, testLogger())
	svc := NewEnvironmentService(mq, reg, testLogger())
	ctx := context.Background()

	agentID := uuid.New()
	envID := uuid.New()
	pgEnvID := toPgUUID(envID)
	pgAgentID := toPgUUID(agentID)

	mq.environments[pgEnvID] = sqlc.KarrEnvironment{
		ID:          pgEnvID,
		AgentID:     pgAgentID,
		Name:        "test-env",
		Image:       "ubuntu:latest",
		ContainerID: "abc123",
		Status:      "stopped",
	}

	err := svc.Start(ctx, envID)
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "no BONNIE client")
}

func TestEnvironmentService_Stop_NoClient(t *testing.T) {
	mq := newMockQuerier()
	reg := bonnie.NewRegistry(nil, testLogger())
	svc := NewEnvironmentService(mq, reg, testLogger())
	ctx := context.Background()

	agentID := uuid.New()
	envID := uuid.New()
	pgEnvID := toPgUUID(envID)
	pgAgentID := toPgUUID(agentID)

	mq.environments[pgEnvID] = sqlc.KarrEnvironment{
		ID:          pgEnvID,
		AgentID:     pgAgentID,
		Name:        "test-env",
		Image:       "ubuntu:latest",
		ContainerID: "abc123",
		Status:      "running",
	}

	err := svc.Stop(ctx, envID)
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "no BONNIE client")
}
