package handlers_test

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/flag-ai/karr/internal/api/handlers"
	"github.com/stretchr/testify/assert"
)

func TestMetricsHandler_Metrics(t *testing.T) {
	h := handlers.NewMetricsHandler()

	req := httptest.NewRequest(http.MethodGet, "/metrics", http.NoBody)
	rr := httptest.NewRecorder()
	h.Metrics(rr, req)

	assert.Equal(t, http.StatusOK, rr.Code)
	// Prometheus handler should return text content with at least some default metrics.
	assert.Contains(t, rr.Body.String(), "go_")
}
