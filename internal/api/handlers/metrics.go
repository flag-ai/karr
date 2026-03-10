package handlers

import (
	"net/http"

	"github.com/prometheus/client_golang/prometheus/promhttp"
)

// MetricsHandler serves Prometheus metrics.
type MetricsHandler struct {
	handler http.Handler
}

// NewMetricsHandler creates a MetricsHandler.
func NewMetricsHandler() *MetricsHandler {
	return &MetricsHandler{
		handler: promhttp.Handler(),
	}
}

// Metrics serves the Prometheus metrics endpoint.
func (h *MetricsHandler) Metrics(w http.ResponseWriter, r *http.Request) {
	h.handler.ServeHTTP(w, r)
}
