package service

import (
	"context"
	"fmt"
	"log/slog"
	"strings"

	"github.com/flag-ai/karr/internal/bonnie"
	"github.com/flag-ai/karr/internal/db/sqlc"
	"github.com/flag-ai/karr/internal/models"
	"github.com/google/uuid"
)

// CreateAgentInput holds the parameters for registering a new agent.
type CreateAgentInput struct {
	Name  string `json:"name"`
	URL   string `json:"url"`
	Token string `json:"token"`
}

// AgentStatusResponse contains agent health and GPU info from the BONNIE agent.
type AgentStatusResponse struct {
	Agent  models.Agent               `json:"agent"`
	System *bonnie.SystemInfoResponse `json:"system,omitempty"`
	GPU    *bonnie.GPUSnapshot        `json:"gpu,omitempty"`
}

// AgentService manages BONNIE agent registration and status.
// It implements AgentServicer.
type AgentService struct {
	queries  Querier
	registry *bonnie.Registry
	logger   *slog.Logger
}

// NewAgentService creates an AgentService.
func NewAgentService(queries Querier, registry *bonnie.Registry, logger *slog.Logger) *AgentService {
	return &AgentService{
		queries:  queries,
		registry: registry,
		logger:   logger,
	}
}

// List returns all registered agents with tokens stripped.
func (s *AgentService) List(ctx context.Context) ([]models.Agent, error) {
	rows, err := s.queries.ListAgents(ctx)
	if err != nil {
		return nil, fmt.Errorf("list agents: %w", err)
	}

	agents := make([]models.Agent, 0, len(rows))
	for _, row := range rows {
		a := agentFromRow(row)
		a.Token = "" // strip token from list responses
		agents = append(agents, a)
	}
	return agents, nil
}

// Get returns a single agent by ID with the token stripped.
func (s *AgentService) Get(ctx context.Context, id uuid.UUID) (models.Agent, error) {
	row, err := s.queries.GetAgent(ctx, toPgUUID(id))
	if err != nil {
		return models.Agent{}, fmt.Errorf("get agent %s: %w", id, err)
	}

	a := agentFromRow(row)
	a.Token = "" // strip token
	return a, nil
}

// Create registers a new BONNIE agent.
func (s *AgentService) Create(ctx context.Context, input CreateAgentInput) (models.Agent, error) {
	// Validate required fields.
	name := strings.TrimSpace(input.Name)
	if name == "" {
		return models.Agent{}, fmt.Errorf("agent name is required")
	}
	url := strings.TrimSpace(input.URL)
	if url == "" {
		return models.Agent{}, fmt.Errorf("agent url is required")
	}

	row, err := s.queries.CreateAgent(ctx, sqlc.CreateAgentParams{
		Name:   name,
		Url:    url,
		Token:  input.Token,
		Status: string(models.AgentStatusOffline),
	})
	if err != nil {
		return models.Agent{}, fmt.Errorf("create agent: %w", err)
	}

	agent := agentFromRow(row)

	// Register the agent with the BONNIE client registry so subsequent
	// calls can reach it.
	s.registry.Register(agent.ID, agent.Name, url, input.Token)

	s.logger.Info("agent registered",
		slog.String("id", agent.ID.String()),
		slog.String("name", agent.Name),
	)

	agent.Token = "" // strip token from response
	return agent, nil
}

// Delete removes an agent from the registry and database.
func (s *AgentService) Delete(ctx context.Context, id uuid.UUID) error {
	// Unregister from BONNIE client registry first.
	s.registry.Unregister(id)

	if err := s.queries.DeleteAgent(ctx, toPgUUID(id)); err != nil {
		return fmt.Errorf("delete agent %s: %w", id, err)
	}

	s.logger.Info("agent deleted", slog.String("id", id.String()))
	return nil
}

// GetStatus queries the live BONNIE agent for system info and GPU status.
func (s *AgentService) GetStatus(ctx context.Context, id uuid.UUID) (AgentStatusResponse, error) {
	row, err := s.queries.GetAgent(ctx, toPgUUID(id))
	if err != nil {
		return AgentStatusResponse{}, fmt.Errorf("get agent %s: %w", id, err)
	}

	agent := agentFromRow(row)
	agent.Token = "" // strip token

	resp := AgentStatusResponse{Agent: agent}

	client, ok := s.registry.Get(id)
	if !ok {
		s.logger.Warn("no BONNIE client registered for agent", slog.String("id", id.String()))
		return resp, nil
	}

	sysInfo, err := client.SystemInfo(ctx)
	if err != nil {
		s.logger.Error("failed to get system info from agent",
			slog.String("id", id.String()),
			slog.String("error", err.Error()),
		)
	} else {
		resp.System = sysInfo
	}

	gpuStatus, err := client.GPUStatus(ctx)
	if err != nil {
		s.logger.Error("failed to get GPU status from agent",
			slog.String("id", id.String()),
			slog.String("error", err.Error()),
		)
	} else {
		resp.GPU = gpuStatus
	}

	return resp, nil
}

// Compile-time check that AgentService satisfies AgentServicer.
var _ AgentServicer = (*AgentService)(nil)
