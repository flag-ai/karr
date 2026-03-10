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

// mockEnvironmentService implements service.EnvironmentServicer for testing.
type mockEnvironmentService struct {
	listFn       func(ctx context.Context) ([]models.Environment, error)
	getFn        func(ctx context.Context, id uuid.UUID) (models.Environment, error)
	createFn     func(ctx context.Context, input service.CreateEnvironmentInput) (models.Environment, error)
	startFn      func(ctx context.Context, id uuid.UUID) error
	stopFn       func(ctx context.Context, id uuid.UUID) error
	removeFn     func(ctx context.Context, id uuid.UUID) error
	streamLogsFn func(ctx context.Context, id uuid.UUID, cb func(string)) error
}

func (m *mockEnvironmentService) List(ctx context.Context) ([]models.Environment, error) {
	return m.listFn(ctx)
}
func (m *mockEnvironmentService) Get(ctx context.Context, id uuid.UUID) (models.Environment, error) {
	return m.getFn(ctx, id)
}

//nolint:gocritic // interface compliance requires value parameter
func (m *mockEnvironmentService) Create(ctx context.Context, input service.CreateEnvironmentInput) (models.Environment, error) {
	return m.createFn(ctx, input)
}
func (m *mockEnvironmentService) Start(ctx context.Context, id uuid.UUID) error {
	return m.startFn(ctx, id)
}
func (m *mockEnvironmentService) Stop(ctx context.Context, id uuid.UUID) error {
	return m.stopFn(ctx, id)
}
func (m *mockEnvironmentService) Remove(ctx context.Context, id uuid.UUID) error {
	return m.removeFn(ctx, id)
}
func (m *mockEnvironmentService) StreamLogs(ctx context.Context, id uuid.UUID, cb func(string)) error {
	return m.streamLogsFn(ctx, id, cb)
}

func newTestEnvironmentHandler(svc *mockEnvironmentService) *handlers.EnvironmentHandler {
	return handlers.NewEnvironmentHandler(svc, slog.Default())
}

func TestEnvironmentHandler_List(t *testing.T) {
	now := time.Now()
	agentID := uuid.New()
	envs := []models.Environment{
		{ID: uuid.New(), AgentID: agentID, Name: "dev-env", Image: "ubuntu:22.04", Status: models.EnvironmentStatusRunning, CreatedAt: now, UpdatedAt: now},
	}

	svc := &mockEnvironmentService{
		listFn: func(_ context.Context) ([]models.Environment, error) {
			return envs, nil
		},
	}
	h := newTestEnvironmentHandler(svc)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/environments", http.NoBody)
	rr := httptest.NewRecorder()
	h.List(rr, req)

	assert.Equal(t, http.StatusOK, rr.Code)

	var result []models.Environment
	require.NoError(t, json.NewDecoder(rr.Body).Decode(&result))
	assert.Len(t, result, 1)
	assert.Equal(t, "dev-env", result[0].Name)
}

func TestEnvironmentHandler_List_Error(t *testing.T) {
	svc := &mockEnvironmentService{
		listFn: func(_ context.Context) ([]models.Environment, error) {
			return nil, errors.New("db error")
		},
	}
	h := newTestEnvironmentHandler(svc)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/environments", http.NoBody)
	rr := httptest.NewRecorder()
	h.List(rr, req)

	assert.Equal(t, http.StatusInternalServerError, rr.Code)
}

func TestEnvironmentHandler_Get(t *testing.T) {
	id := uuid.New()
	agentID := uuid.New()
	now := time.Now()
	env := models.Environment{ID: id, AgentID: agentID, Name: "dev-env", Image: "ubuntu:22.04", Status: models.EnvironmentStatusRunning, CreatedAt: now, UpdatedAt: now}

	svc := &mockEnvironmentService{
		getFn: func(_ context.Context, gotID uuid.UUID) (models.Environment, error) {
			assert.Equal(t, id, gotID)
			return env, nil
		},
	}
	h := newTestEnvironmentHandler(svc)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/environments/"+id.String(), http.NoBody)
	req = withChiURLParam(req, id.String())
	rr := httptest.NewRecorder()
	h.Get(rr, req)

	assert.Equal(t, http.StatusOK, rr.Code)
}

func TestEnvironmentHandler_Get_InvalidID(t *testing.T) {
	svc := &mockEnvironmentService{}
	h := newTestEnvironmentHandler(svc)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/environments/bad", http.NoBody)
	req = withChiURLParam(req, "bad")
	rr := httptest.NewRecorder()
	h.Get(rr, req)

	assert.Equal(t, http.StatusBadRequest, rr.Code)
}

func TestEnvironmentHandler_Create(t *testing.T) {
	id := uuid.New()
	agentID := uuid.New()
	now := time.Now()

	svc := &mockEnvironmentService{
		createFn: func(_ context.Context, input service.CreateEnvironmentInput) (models.Environment, error) {
			assert.Equal(t, "dev-env", input.Name)
			return models.Environment{
				ID: id, AgentID: agentID, Name: input.Name, Image: input.Image,
				Status: models.EnvironmentStatusCreating, CreatedAt: now, UpdatedAt: now,
			}, nil
		},
	}
	h := newTestEnvironmentHandler(svc)

	body, _ := json.Marshal(service.CreateEnvironmentInput{
		Name: "dev-env", Image: "ubuntu:22.04", AgentID: agentID,
	})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/environments", bytes.NewReader(body))
	rr := httptest.NewRecorder()
	h.Create(rr, req)

	assert.Equal(t, http.StatusCreated, rr.Code)
}

func TestEnvironmentHandler_Create_MissingFields(t *testing.T) {
	svc := &mockEnvironmentService{}
	h := newTestEnvironmentHandler(svc)

	body, _ := json.Marshal(service.CreateEnvironmentInput{Name: ""})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/environments", bytes.NewReader(body))
	rr := httptest.NewRecorder()
	h.Create(rr, req)

	assert.Equal(t, http.StatusBadRequest, rr.Code)
}

func TestEnvironmentHandler_Start(t *testing.T) {
	id := uuid.New()

	svc := &mockEnvironmentService{
		startFn: func(_ context.Context, gotID uuid.UUID) error {
			assert.Equal(t, id, gotID)
			return nil
		},
	}
	h := newTestEnvironmentHandler(svc)

	req := httptest.NewRequest(http.MethodPost, "/api/v1/environments/"+id.String()+"/start", http.NoBody)
	req = withChiURLParam(req, id.String())
	rr := httptest.NewRecorder()
	h.Start(rr, req)

	assert.Equal(t, http.StatusNoContent, rr.Code)
}

func TestEnvironmentHandler_Start_Error(t *testing.T) {
	id := uuid.New()

	svc := &mockEnvironmentService{
		startFn: func(_ context.Context, _ uuid.UUID) error {
			return errors.New("container not found")
		},
	}
	h := newTestEnvironmentHandler(svc)

	req := httptest.NewRequest(http.MethodPost, "/api/v1/environments/"+id.String()+"/start", http.NoBody)
	req = withChiURLParam(req, id.String())
	rr := httptest.NewRecorder()
	h.Start(rr, req)

	assert.Equal(t, http.StatusInternalServerError, rr.Code)
}

func TestEnvironmentHandler_Stop(t *testing.T) {
	id := uuid.New()

	svc := &mockEnvironmentService{
		stopFn: func(_ context.Context, gotID uuid.UUID) error {
			assert.Equal(t, id, gotID)
			return nil
		},
	}
	h := newTestEnvironmentHandler(svc)

	req := httptest.NewRequest(http.MethodPost, "/api/v1/environments/"+id.String()+"/stop", http.NoBody)
	req = withChiURLParam(req, id.String())
	rr := httptest.NewRecorder()
	h.Stop(rr, req)

	assert.Equal(t, http.StatusNoContent, rr.Code)
}

func TestEnvironmentHandler_Remove(t *testing.T) {
	id := uuid.New()

	svc := &mockEnvironmentService{
		removeFn: func(_ context.Context, gotID uuid.UUID) error {
			assert.Equal(t, id, gotID)
			return nil
		},
	}
	h := newTestEnvironmentHandler(svc)

	req := httptest.NewRequest(http.MethodDelete, "/api/v1/environments/"+id.String(), http.NoBody)
	req = withChiURLParam(req, id.String())
	rr := httptest.NewRecorder()
	h.Remove(rr, req)

	assert.Equal(t, http.StatusNoContent, rr.Code)
}

func TestEnvironmentHandler_Logs(t *testing.T) {
	id := uuid.New()

	svc := &mockEnvironmentService{
		streamLogsFn: func(_ context.Context, gotID uuid.UUID, cb func(string)) error {
			assert.Equal(t, id, gotID)
			cb("hello from container")
			cb("second line")
			return nil
		},
	}
	h := newTestEnvironmentHandler(svc)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/environments/"+id.String()+"/logs", http.NoBody)
	req = withChiURLParam(req, id.String())
	rr := httptest.NewRecorder()
	h.Logs(rr, req)

	assert.Equal(t, http.StatusOK, rr.Code)
	assert.Equal(t, "text/event-stream", rr.Header().Get("Content-Type"))
	assert.Contains(t, rr.Body.String(), "data: hello from container")
	assert.Contains(t, rr.Body.String(), "data: second line")
}
