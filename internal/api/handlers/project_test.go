package handlers_test

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/flag-ai/karr/internal/api/handlers"
	"github.com/flag-ai/karr/internal/models"
	"github.com/flag-ai/karr/internal/service"
)

// mockProjectService implements service.ProjectServicer for testing.
type mockProjectService struct {
	listFn   func(ctx context.Context) ([]models.Project, error)
	getFn    func(ctx context.Context, id uuid.UUID) (models.Project, error)
	createFn func(ctx context.Context, input service.CreateProjectInput) (models.Project, error)
	updateFn func(ctx context.Context, id uuid.UUID, input service.UpdateProjectInput) (models.Project, error)
	deleteFn func(ctx context.Context, id uuid.UUID) error
}

func (m *mockProjectService) List(ctx context.Context) ([]models.Project, error) {
	return m.listFn(ctx)
}
func (m *mockProjectService) Get(ctx context.Context, id uuid.UUID) (models.Project, error) {
	return m.getFn(ctx, id)
}
func (m *mockProjectService) Create(ctx context.Context, input service.CreateProjectInput) (models.Project, error) {
	return m.createFn(ctx, input)
}
func (m *mockProjectService) Update(ctx context.Context, id uuid.UUID, input service.UpdateProjectInput) (models.Project, error) {
	return m.updateFn(ctx, id, input)
}
func (m *mockProjectService) Delete(ctx context.Context, id uuid.UUID) error {
	return m.deleteFn(ctx, id)
}

func newTestProjectHandler(svc *mockProjectService) *handlers.ProjectHandler {
	return handlers.NewProjectHandler(svc, slog.Default())
}

func TestProjectHandler_List(t *testing.T) {
	now := time.Now()
	projects := []models.Project{
		{ID: uuid.New(), Name: "my-project", CreatedAt: now, UpdatedAt: now},
	}

	svc := &mockProjectService{
		listFn: func(_ context.Context) ([]models.Project, error) {
			return projects, nil
		},
	}
	h := newTestProjectHandler(svc)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/projects", http.NoBody)
	rr := httptest.NewRecorder()
	h.List(rr, req)

	assert.Equal(t, http.StatusOK, rr.Code)

	var result []models.Project
	require.NoError(t, json.NewDecoder(rr.Body).Decode(&result))
	assert.Len(t, result, 1)
	assert.Equal(t, "my-project", result[0].Name)
}

func TestProjectHandler_List_Error(t *testing.T) {
	svc := &mockProjectService{
		listFn: func(_ context.Context) ([]models.Project, error) {
			return nil, errors.New("db error")
		},
	}
	h := newTestProjectHandler(svc)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/projects", http.NoBody)
	rr := httptest.NewRecorder()
	h.List(rr, req)

	assert.Equal(t, http.StatusInternalServerError, rr.Code)
}

func TestProjectHandler_Get(t *testing.T) {
	id := uuid.New()
	now := time.Now()
	project := models.Project{ID: id, Name: "my-project", CreatedAt: now, UpdatedAt: now}

	svc := &mockProjectService{
		getFn: func(_ context.Context, gotID uuid.UUID) (models.Project, error) {
			assert.Equal(t, id, gotID)
			return project, nil
		},
	}
	h := newTestProjectHandler(svc)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/projects/"+id.String(), http.NoBody)
	req = withChiURLParam(req, id.String())
	rr := httptest.NewRecorder()
	h.Get(rr, req)

	assert.Equal(t, http.StatusOK, rr.Code)
}

func TestProjectHandler_Get_InvalidID(t *testing.T) {
	svc := &mockProjectService{}
	h := newTestProjectHandler(svc)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/projects/bad", http.NoBody)
	req = withChiURLParam(req, "bad")
	rr := httptest.NewRecorder()
	h.Get(rr, req)

	assert.Equal(t, http.StatusBadRequest, rr.Code)
}

func TestProjectHandler_Create(t *testing.T) {
	id := uuid.New()
	now := time.Now()

	svc := &mockProjectService{
		createFn: func(_ context.Context, input service.CreateProjectInput) (models.Project, error) {
			assert.Equal(t, "my-project", input.Name)
			return models.Project{ID: id, Name: input.Name, CreatedAt: now, UpdatedAt: now}, nil
		},
	}
	h := newTestProjectHandler(svc)

	body, _ := json.Marshal(service.CreateProjectInput{Name: "my-project"})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/projects", bytes.NewReader(body))
	rr := httptest.NewRecorder()
	h.Create(rr, req)

	assert.Equal(t, http.StatusCreated, rr.Code)
}

func TestProjectHandler_Create_MissingName(t *testing.T) {
	svc := &mockProjectService{}
	h := newTestProjectHandler(svc)

	body, _ := json.Marshal(service.CreateProjectInput{})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/projects", bytes.NewReader(body))
	rr := httptest.NewRecorder()
	h.Create(rr, req)

	assert.Equal(t, http.StatusBadRequest, rr.Code)
}

func TestProjectHandler_Update(t *testing.T) {
	id := uuid.New()
	now := time.Now()

	newName := "updated"
	svc := &mockProjectService{
		updateFn: func(_ context.Context, gotID uuid.UUID, input service.UpdateProjectInput) (models.Project, error) {
			assert.Equal(t, id, gotID)
			return models.Project{ID: id, Name: *input.Name, CreatedAt: now, UpdatedAt: now}, nil
		},
	}
	h := newTestProjectHandler(svc)

	body, _ := json.Marshal(service.UpdateProjectInput{Name: &newName})
	req := httptest.NewRequest(http.MethodPut, "/api/v1/projects/"+id.String(), bytes.NewReader(body))
	req = withChiURLParam(req, id.String())
	rr := httptest.NewRecorder()
	h.Update(rr, req)

	assert.Equal(t, http.StatusOK, rr.Code)
}

func TestProjectHandler_Delete(t *testing.T) {
	id := uuid.New()

	svc := &mockProjectService{
		deleteFn: func(_ context.Context, gotID uuid.UUID) error {
			assert.Equal(t, id, gotID)
			return nil
		},
	}
	h := newTestProjectHandler(svc)

	req := httptest.NewRequest(http.MethodDelete, "/api/v1/projects/"+id.String(), http.NoBody)
	req = withChiURLParam(req, id.String())
	rr := httptest.NewRecorder()
	h.Delete(rr, req)

	assert.Equal(t, http.StatusNoContent, rr.Code)
}
