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

// CreateEnvironmentInput holds the parameters for creating a new environment.
type CreateEnvironmentInput struct {
	ProjectID *uuid.UUID `json:"project_id,omitempty"`
	AgentID   uuid.UUID  `json:"agent_id"`
	Name      string     `json:"name"`
	Image     string     `json:"image"`
	GPU       bool       `json:"gpu"`
	Env       []string   `json:"env,omitempty"`
	Mounts    []string   `json:"mounts,omitempty"`
	Command   []string   `json:"command,omitempty"`
}

// EnvironmentService orchestrates environment lifecycle management.
// It implements EnvironmentServicer.
type EnvironmentService struct {
	queries  Querier
	registry *bonnie.Registry
	logger   *slog.Logger
}

// NewEnvironmentService creates an EnvironmentService.
func NewEnvironmentService(queries Querier, registry *bonnie.Registry, logger *slog.Logger) *EnvironmentService {
	return &EnvironmentService{
		queries:  queries,
		registry: registry,
		logger:   logger,
	}
}

// List returns all environments.
func (s *EnvironmentService) List(ctx context.Context) ([]models.Environment, error) {
	rows, err := s.queries.ListEnvironments(ctx)
	if err != nil {
		return nil, fmt.Errorf("list environments: %w", err)
	}

	envs := make([]models.Environment, 0, len(rows))
	for i := range rows {
		envs = append(envs, environmentFromRow(rows[i]))
	}
	return envs, nil
}

// ListByAgent returns all environments for a given agent.
func (s *EnvironmentService) ListByAgent(ctx context.Context, agentID uuid.UUID) ([]models.Environment, error) {
	rows, err := s.queries.ListEnvironmentsByAgent(ctx, toPgUUID(agentID))
	if err != nil {
		return nil, fmt.Errorf("list environments by agent %s: %w", agentID, err)
	}

	envs := make([]models.Environment, 0, len(rows))
	for i := range rows {
		envs = append(envs, environmentFromRow(rows[i]))
	}
	return envs, nil
}

// ListByProject returns all environments for a given project.
func (s *EnvironmentService) ListByProject(ctx context.Context, projectID uuid.UUID) ([]models.Environment, error) {
	rows, err := s.queries.ListEnvironmentsByProject(ctx, toPgUUID(projectID))
	if err != nil {
		return nil, fmt.Errorf("list environments by project %s: %w", projectID, err)
	}

	envs := make([]models.Environment, 0, len(rows))
	for i := range rows {
		envs = append(envs, environmentFromRow(rows[i]))
	}
	return envs, nil
}

// Get returns a single environment by ID.
func (s *EnvironmentService) Get(ctx context.Context, id uuid.UUID) (models.Environment, error) {
	row, err := s.queries.GetEnvironment(ctx, toPgUUID(id))
	if err != nil {
		return models.Environment{}, fmt.Errorf("get environment %s: %w", id, err)
	}
	return environmentFromRow(row), nil
}

// Create provisions a new environment: persists it to the DB and creates
// a container on the BONNIE agent.
//
// Flow:
//  1. CreateEnvironment in DB (status=creating)
//  2. Get BONNIE client from registry by agent_id
//  3. Call bonnie.CreateContainer
//  4. UpdateEnvironmentContainerID with returned container ID
//  5. UpdateEnvironmentStatus to "stopped" (created but not started)
//  6. If BONNIE call fails, UpdateEnvironmentStatus to "error"
//
//nolint:gocritic // simpler API than pointer for callers
func (s *EnvironmentService) Create(ctx context.Context, input CreateEnvironmentInput) (models.Environment, error) {
	name := strings.TrimSpace(input.Name)
	if name == "" {
		return models.Environment{}, fmt.Errorf("environment name is required")
	}
	image := strings.TrimSpace(input.Image)
	if image == "" {
		return models.Environment{}, fmt.Errorf("environment image is required")
	}

	// Build DB params.
	params := sqlc.CreateEnvironmentParams{
		AgentID: toPgUUID(input.AgentID),
		Name:    name,
		Image:   image,
		Gpu:     input.GPU,
		Env:     marshalJSONB(input.Env),
		Mounts:  marshalJSONB(input.Mounts),
		Command: marshalJSONB(input.Command),
	}
	if input.ProjectID != nil {
		params.ProjectID = toPgUUID(*input.ProjectID)
	}

	// Step 1: Persist environment in DB with status=creating.
	row, err := s.queries.CreateEnvironment(ctx, params)
	if err != nil {
		return models.Environment{}, fmt.Errorf("create environment in db: %w", err)
	}

	envID := row.ID

	// Step 2: Get BONNIE client for the agent.
	client, ok := s.registry.Get(input.AgentID)
	if !ok {
		_ = s.queries.UpdateEnvironmentStatus(ctx, sqlc.UpdateEnvironmentStatusParams{
			ID:     envID,
			Status: string(models.EnvironmentStatusError),
		})
		return models.Environment{}, fmt.Errorf("no BONNIE client registered for agent %s", input.AgentID)
	}

	// Step 3: Create container on the BONNIE agent.
	containerID, err := client.CreateContainer(ctx, &bonnie.CreateContainerRequest{
		Name:    name,
		Image:   image,
		Env:     input.Env,
		Mounts:  input.Mounts,
		GPU:     input.GPU,
		Command: input.Command,
	})
	if err != nil {
		// Mark as error in DB.
		_ = s.queries.UpdateEnvironmentStatus(ctx, sqlc.UpdateEnvironmentStatusParams{
			ID:     envID,
			Status: string(models.EnvironmentStatusError),
		})
		return models.Environment{}, fmt.Errorf("create container on agent %s: %w", input.AgentID, err)
	}

	// Step 4: Update container ID.
	if err := s.queries.UpdateEnvironmentContainerID(ctx, sqlc.UpdateEnvironmentContainerIDParams{
		ID:          envID,
		ContainerID: containerID,
	}); err != nil {
		return models.Environment{}, fmt.Errorf("update container id: %w", err)
	}

	// Step 5: Update status to stopped (created but not started).
	if err := s.queries.UpdateEnvironmentStatus(ctx, sqlc.UpdateEnvironmentStatusParams{
		ID:     envID,
		Status: string(models.EnvironmentStatusStopped),
	}); err != nil {
		return models.Environment{}, fmt.Errorf("update environment status: %w", err)
	}

	env := environmentFromRow(row)
	env.ContainerID = containerID
	env.Status = models.EnvironmentStatusStopped

	s.logger.Info("environment created",
		slog.String("id", env.ID.String()),
		slog.String("name", env.Name),
		slog.String("container_id", containerID),
	)
	return env, nil
}

// Start starts a stopped environment's container.
func (s *EnvironmentService) Start(ctx context.Context, id uuid.UUID) error {
	env, client, err := s.getEnvAndClient(ctx, id)
	if err != nil {
		return err
	}

	if err := client.StartContainer(ctx, env.ContainerID); err != nil {
		return fmt.Errorf("start container %s: %w", env.ContainerID, err)
	}

	if err := s.queries.UpdateEnvironmentStatus(ctx, sqlc.UpdateEnvironmentStatusParams{
		ID:     toPgUUID(id),
		Status: string(models.EnvironmentStatusRunning),
	}); err != nil {
		return fmt.Errorf("update environment status: %w", err)
	}

	s.logger.Info("environment started", slog.String("id", id.String()))
	return nil
}

// Stop stops a running environment's container.
func (s *EnvironmentService) Stop(ctx context.Context, id uuid.UUID) error {
	env, client, err := s.getEnvAndClient(ctx, id)
	if err != nil {
		return err
	}

	if err := client.StopContainer(ctx, env.ContainerID); err != nil {
		return fmt.Errorf("stop container %s: %w", env.ContainerID, err)
	}

	if err := s.queries.UpdateEnvironmentStatus(ctx, sqlc.UpdateEnvironmentStatusParams{
		ID:     toPgUUID(id),
		Status: string(models.EnvironmentStatusStopped),
	}); err != nil {
		return fmt.Errorf("update environment status: %w", err)
	}

	s.logger.Info("environment stopped", slog.String("id", id.String()))
	return nil
}

// Remove removes an environment's container and deletes it from the DB.
func (s *EnvironmentService) Remove(ctx context.Context, id uuid.UUID) error {
	env, client, err := s.getEnvAndClient(ctx, id)
	if err != nil {
		return err
	}

	if env.ContainerID != "" {
		if err := client.RemoveContainer(ctx, env.ContainerID); err != nil {
			s.logger.Error("failed to remove container from agent",
				slog.String("id", id.String()),
				slog.String("container_id", env.ContainerID),
				slog.String("error", err.Error()),
			)
			_ = s.queries.UpdateEnvironmentStatus(ctx, sqlc.UpdateEnvironmentStatusParams{
				ID:     toPgUUID(id),
				Status: string(models.EnvironmentStatusError),
			})
			return fmt.Errorf("remove container %s: %w", env.ContainerID, err)
		}
	}

	if err := s.queries.DeleteEnvironment(ctx, toPgUUID(id)); err != nil {
		return fmt.Errorf("delete environment %s: %w", id, err)
	}

	s.logger.Info("environment removed", slog.String("id", id.String()))
	return nil
}

// StreamLogs proxies container logs from the BONNIE agent.
func (s *EnvironmentService) StreamLogs(ctx context.Context, id uuid.UUID, callback func(string)) error {
	env, client, err := s.getEnvAndClient(ctx, id)
	if err != nil {
		return err
	}

	if env.ContainerID == "" {
		return fmt.Errorf("environment %s has no container", id)
	}

	return client.StreamLogs(ctx, env.ContainerID, callback)
}

// getEnvAndClient fetches an environment from the DB and resolves the BONNIE
// client for its agent. This is a common prerequisite for lifecycle operations.
func (s *EnvironmentService) getEnvAndClient(ctx context.Context, id uuid.UUID) (models.Environment, bonnie.Client, error) {
	row, err := s.queries.GetEnvironment(ctx, toPgUUID(id))
	if err != nil {
		return models.Environment{}, nil, fmt.Errorf("get environment %s: %w", id, err)
	}

	env := environmentFromRow(row)

	client, ok := s.registry.Get(env.AgentID)
	if !ok {
		return models.Environment{}, nil, fmt.Errorf("no BONNIE client registered for agent %s", env.AgentID)
	}

	return env, client, nil
}

// Compile-time check that EnvironmentService satisfies EnvironmentServicer.
var _ EnvironmentServicer = (*EnvironmentService)(nil)
