package service

import (
	"context"
	"fmt"
	"log/slog"
	"strings"

	"github.com/flag-ai/karr/internal/db/sqlc"
	"github.com/flag-ai/karr/internal/models"
	"github.com/google/uuid"
)

// CreateProjectInput holds the parameters for creating a new project.
type CreateProjectInput struct {
	Name        string `json:"name"`
	Description string `json:"description"`
}

// UpdateProjectInput holds the parameters for updating a project.
// Nil fields are left unchanged.
type UpdateProjectInput struct {
	Name        *string `json:"name,omitempty"`
	Description *string `json:"description,omitempty"`
}

// ProjectService manages project CRUD operations.
// It implements ProjectServicer.
type ProjectService struct {
	queries Querier
	logger  *slog.Logger
}

// NewProjectService creates a ProjectService.
func NewProjectService(queries Querier, logger *slog.Logger) *ProjectService {
	return &ProjectService{
		queries: queries,
		logger:  logger,
	}
}

// List returns all projects.
func (s *ProjectService) List(ctx context.Context) ([]models.Project, error) {
	rows, err := s.queries.ListProjects(ctx)
	if err != nil {
		return nil, fmt.Errorf("list projects: %w", err)
	}

	projects := make([]models.Project, 0, len(rows))
	for i := range rows {
		projects = append(projects, projectFromRow(rows[i]))
	}
	return projects, nil
}

// Get returns a single project by ID.
func (s *ProjectService) Get(ctx context.Context, id uuid.UUID) (models.Project, error) {
	row, err := s.queries.GetProject(ctx, toPgUUID(id))
	if err != nil {
		return models.Project{}, fmt.Errorf("get project %s: %w", id, err)
	}
	return projectFromRow(row), nil
}

// Create persists a new project.
func (s *ProjectService) Create(ctx context.Context, input CreateProjectInput) (models.Project, error) {
	name := strings.TrimSpace(input.Name)
	if name == "" {
		return models.Project{}, fmt.Errorf("project name is required")
	}

	row, err := s.queries.CreateProject(ctx, sqlc.CreateProjectParams{
		Name:        name,
		Description: strings.TrimSpace(input.Description),
	})
	if err != nil {
		return models.Project{}, fmt.Errorf("create project: %w", err)
	}

	project := projectFromRow(row)
	s.logger.Info("project created",
		slog.String("id", project.ID.String()),
		slog.String("name", project.Name),
	)
	return project, nil
}

// Update modifies an existing project. Only non-nil fields are applied.
func (s *ProjectService) Update(ctx context.Context, id uuid.UUID, input UpdateProjectInput) (models.Project, error) {
	// Fetch the current project to apply partial updates.
	current, err := s.queries.GetProject(ctx, toPgUUID(id))
	if err != nil {
		return models.Project{}, fmt.Errorf("get project %s for update: %w", id, err)
	}

	name := current.Name
	if input.Name != nil {
		name = strings.TrimSpace(*input.Name)
	}
	if name == "" {
		return models.Project{}, fmt.Errorf("project name is required")
	}

	description := current.Description
	if input.Description != nil {
		description = strings.TrimSpace(*input.Description)
	}

	row, err := s.queries.UpdateProject(ctx, sqlc.UpdateProjectParams{
		ID:          toPgUUID(id),
		Name:        name,
		Description: description,
	})
	if err != nil {
		return models.Project{}, fmt.Errorf("update project %s: %w", id, err)
	}

	project := projectFromRow(row)
	s.logger.Info("project updated",
		slog.String("id", project.ID.String()),
		slog.String("name", project.Name),
	)
	return project, nil
}

// Delete removes a project by ID.
func (s *ProjectService) Delete(ctx context.Context, id uuid.UUID) error {
	if err := s.queries.DeleteProject(ctx, toPgUUID(id)); err != nil {
		return fmt.Errorf("delete project %s: %w", id, err)
	}

	s.logger.Info("project deleted", slog.String("id", id.String()))
	return nil
}

// Compile-time check that ProjectService satisfies ProjectServicer.
var _ ProjectServicer = (*ProjectService)(nil)
