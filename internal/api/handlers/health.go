package handlers

import (
	"log/slog"
	"net/http"

	"github.com/flag-ai/commons/health"
	"github.com/flag-ai/commons/version"
)

// HealthHandler serves health and readiness endpoints.
type HealthHandler struct {
	registry *health.Registry
	logger   *slog.Logger
}

// NewHealthHandler creates a HealthHandler.
func NewHealthHandler(registry *health.Registry, logger *slog.Logger) *HealthHandler {
	return &HealthHandler{
		registry: registry,
		logger:   logger,
	}
}

// Health returns 200 with version info. This is a liveness check —
// it does not probe dependencies.
func (h *HealthHandler) Health(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{
		"status":  "ok",
		"version": version.Info(),
	})
}

// Ready runs all registered health checks and returns the aggregate report.
// Returns 200 if all checks pass, 503 otherwise.
func (h *HealthHandler) Ready(w http.ResponseWriter, r *http.Request) {
	report := h.registry.RunAll(r.Context())

	status := http.StatusOK
	if !report.Healthy {
		status = http.StatusServiceUnavailable
	}

	writeJSON(w, status, report)
}
