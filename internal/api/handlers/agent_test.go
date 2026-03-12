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

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/flag-ai/karr/internal/api/handlers"
	"github.com/flag-ai/karr/internal/models"
	"github.com/flag-ai/karr/internal/service"
)

// mockAgentService implements service.AgentServicer for testing.
type mockAgentService struct {
	listFn      func(ctx context.Context) ([]models.Agent, error)
	getFn       func(ctx context.Context, id uuid.UUID) (models.Agent, error)
	createFn    func(ctx context.Context, input service.CreateAgentInput) (models.Agent, error)
	deleteFn    func(ctx context.Context, id uuid.UUID) error
	getStatusFn func(ctx context.Context, id uuid.UUID) (service.AgentStatusResponse, error)
}

func (m *mockAgentService) List(ctx context.Context) ([]models.Agent, error) {
	return m.listFn(ctx)
}
func (m *mockAgentService) Get(ctx context.Context, id uuid.UUID) (models.Agent, error) {
	return m.getFn(ctx, id)
}
func (m *mockAgentService) Create(ctx context.Context, input service.CreateAgentInput) (models.Agent, error) {
	return m.createFn(ctx, input)
}
func (m *mockAgentService) Delete(ctx context.Context, id uuid.UUID) error {
	return m.deleteFn(ctx, id)
}
func (m *mockAgentService) GetStatus(ctx context.Context, id uuid.UUID) (service.AgentStatusResponse, error) {
	return m.getStatusFn(ctx, id)
}

func newTestAgentHandler(svc *mockAgentService) *handlers.AgentHandler {
	return handlers.NewAgentHandler(svc, slog.Default())
}

// withChiURLParam adds the "id" chi URL parameter to the request context.
func withChiURLParam(r *http.Request, val string) *http.Request {
	rctx := chi.NewRouteContext()
	rctx.URLParams.Add("id", val)
	return r.WithContext(context.WithValue(r.Context(), chi.RouteCtxKey, rctx))
}

func TestAgentHandler_List(t *testing.T) {
	now := time.Now()
	agents := []models.Agent{
		{ID: uuid.New(), Name: "gpu-1", Status: models.AgentStatusOnline, CreatedAt: now, UpdatedAt: now},
	}

	svc := &mockAgentService{
		listFn: func(_ context.Context) ([]models.Agent, error) {
			return agents, nil
		},
	}
	h := newTestAgentHandler(svc)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/agents", http.NoBody)
	rr := httptest.NewRecorder()
	h.List(rr, req)

	assert.Equal(t, http.StatusOK, rr.Code)

	var result []models.Agent
	require.NoError(t, json.NewDecoder(rr.Body).Decode(&result))
	assert.Len(t, result, 1)
	assert.Equal(t, "gpu-1", result[0].Name)
}

func TestAgentHandler_List_Error(t *testing.T) {
	svc := &mockAgentService{
		listFn: func(_ context.Context) ([]models.Agent, error) {
			return nil, errors.New("db error")
		},
	}
	h := newTestAgentHandler(svc)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/agents", http.NoBody)
	rr := httptest.NewRecorder()
	h.List(rr, req)

	assert.Equal(t, http.StatusInternalServerError, rr.Code)
}

func TestAgentHandler_Get(t *testing.T) {
	id := uuid.New()
	now := time.Now()
	agent := models.Agent{ID: id, Name: "gpu-1", Status: models.AgentStatusOnline, CreatedAt: now, UpdatedAt: now}

	svc := &mockAgentService{
		getFn: func(_ context.Context, gotID uuid.UUID) (models.Agent, error) {
			assert.Equal(t, id, gotID)
			return agent, nil
		},
	}
	h := newTestAgentHandler(svc)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/agents/"+id.String(), http.NoBody)
	req = withChiURLParam(req, id.String())
	rr := httptest.NewRecorder()
	h.Get(rr, req)

	assert.Equal(t, http.StatusOK, rr.Code)

	var result models.Agent
	require.NoError(t, json.NewDecoder(rr.Body).Decode(&result))
	assert.Equal(t, "gpu-1", result.Name)
}

func TestAgentHandler_Get_InvalidID(t *testing.T) {
	svc := &mockAgentService{}
	h := newTestAgentHandler(svc)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/agents/not-a-uuid", http.NoBody)
	req = withChiURLParam(req, "not-a-uuid")
	rr := httptest.NewRecorder()
	h.Get(rr, req)

	assert.Equal(t, http.StatusBadRequest, rr.Code)
}

func TestAgentHandler_Create(t *testing.T) {
	id := uuid.New()
	now := time.Now()

	svc := &mockAgentService{
		createFn: func(_ context.Context, input service.CreateAgentInput) (models.Agent, error) {
			assert.Equal(t, "gpu-1", input.Name)
			return models.Agent{ID: id, Name: input.Name, URL: input.URL, Status: models.AgentStatusOffline, CreatedAt: now, UpdatedAt: now}, nil
		},
	}
	h := newTestAgentHandler(svc)

	body, _ := json.Marshal(service.CreateAgentInput{Name: "gpu-1", URL: "http://localhost:8080"})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/agents", bytes.NewReader(body))
	rr := httptest.NewRecorder()
	h.Create(rr, req)

	assert.Equal(t, http.StatusCreated, rr.Code)
}

func TestAgentHandler_Create_MissingFields(t *testing.T) {
	svc := &mockAgentService{}
	h := newTestAgentHandler(svc)

	body, _ := json.Marshal(service.CreateAgentInput{Name: ""})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/agents", bytes.NewReader(body))
	rr := httptest.NewRecorder()
	h.Create(rr, req)

	assert.Equal(t, http.StatusBadRequest, rr.Code)
}

func TestAgentHandler_Delete(t *testing.T) {
	id := uuid.New()

	svc := &mockAgentService{
		deleteFn: func(_ context.Context, gotID uuid.UUID) error {
			assert.Equal(t, id, gotID)
			return nil
		},
	}
	h := newTestAgentHandler(svc)

	req := httptest.NewRequest(http.MethodDelete, "/api/v1/agents/"+id.String(), http.NoBody)
	req = withChiURLParam(req, id.String())
	rr := httptest.NewRecorder()
	h.Delete(rr, req)

	assert.Equal(t, http.StatusNoContent, rr.Code)
}

func TestAgentHandler_GetStatus(t *testing.T) {
	id := uuid.New()
	now := time.Now()
	status := service.AgentStatusResponse{
		Agent: models.Agent{ID: id, Name: "gpu-1", Status: models.AgentStatusOnline, CreatedAt: now, UpdatedAt: now},
	}

	svc := &mockAgentService{
		getStatusFn: func(_ context.Context, gotID uuid.UUID) (service.AgentStatusResponse, error) {
			assert.Equal(t, id, gotID)
			return status, nil
		},
	}
	h := newTestAgentHandler(svc)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/agents/"+id.String()+"/status", http.NoBody)
	req = withChiURLParam(req, id.String())
	rr := httptest.NewRecorder()
	h.GetStatus(rr, req)

	assert.Equal(t, http.StatusOK, rr.Code)
}
