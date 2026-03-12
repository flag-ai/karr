package handlers_test

import (
	"encoding/json"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/flag-ai/commons/health"
	"github.com/flag-ai/karr/internal/api/handlers"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestHealthHandler_Health(t *testing.T) {
	logger := slog.Default()
	registry := health.NewRegistry()
	h := handlers.NewHealthHandler(registry, logger)

	req := httptest.NewRequest(http.MethodGet, "/health", http.NoBody)
	rr := httptest.NewRecorder()

	h.Health(rr, req)

	assert.Equal(t, http.StatusOK, rr.Code)

	var body map[string]string
	require.NoError(t, json.NewDecoder(rr.Body).Decode(&body))
	assert.Equal(t, "ok", body["status"])
	assert.NotEmpty(t, body["version"])
}

func TestHealthHandler_Ready_NoCheckers(t *testing.T) {
	logger := slog.Default()
	registry := health.NewRegistry()
	h := handlers.NewHealthHandler(registry, logger)

	req := httptest.NewRequest(http.MethodGet, "/ready", http.NoBody)
	rr := httptest.NewRecorder()

	h.Ready(rr, req)

	assert.Equal(t, http.StatusOK, rr.Code)

	var report health.Report
	require.NoError(t, json.NewDecoder(rr.Body).Decode(&report))
	assert.True(t, report.Healthy)
}
