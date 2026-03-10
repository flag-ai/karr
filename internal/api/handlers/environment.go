package handlers

import (
	"fmt"
	"log/slog"
	"net/http"

	"github.com/flag-ai/karr/internal/service"
)

// EnvironmentHandler serves environment-related HTTP endpoints.
type EnvironmentHandler struct {
	service service.EnvironmentServicer
	logger  *slog.Logger
}

// NewEnvironmentHandler creates an EnvironmentHandler.
func NewEnvironmentHandler(svc service.EnvironmentServicer, logger *slog.Logger) *EnvironmentHandler {
	return &EnvironmentHandler{
		service: svc,
		logger:  logger,
	}
}

// List returns all environments.
func (h *EnvironmentHandler) List(w http.ResponseWriter, r *http.Request) {
	envs, err := h.service.List(r.Context())
	if err != nil {
		h.logger.Error("list environments", "error", err)
		writeError(w, http.StatusInternalServerError, "failed to list environments")
		return
	}
	writeJSON(w, http.StatusOK, envs)
}

// Get returns a single environment by ID.
func (h *EnvironmentHandler) Get(w http.ResponseWriter, r *http.Request) {
	id, err := parseUUID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid environment id")
		return
	}

	env, err := h.service.Get(r.Context(), id)
	if err != nil {
		h.logger.Error("get environment", "id", id, "error", err)
		writeError(w, http.StatusNotFound, "environment not found")
		return
	}
	writeJSON(w, http.StatusOK, env)
}

// Create provisions a new environment.
func (h *EnvironmentHandler) Create(w http.ResponseWriter, r *http.Request) {
	var input service.CreateEnvironmentInput
	if err := decodeBody(r, &input); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}

	if input.Name == "" || input.Image == "" {
		writeError(w, http.StatusBadRequest, "name and image are required")
		return
	}

	env, err := h.service.Create(r.Context(), input)
	if err != nil {
		h.logger.Error("create environment", "error", err)
		writeError(w, http.StatusInternalServerError, "failed to create environment")
		return
	}
	writeJSON(w, http.StatusCreated, env)
}

// Start starts a stopped environment.
func (h *EnvironmentHandler) Start(w http.ResponseWriter, r *http.Request) {
	id, err := parseUUID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid environment id")
		return
	}

	if err := h.service.Start(r.Context(), id); err != nil {
		h.logger.Error("start environment", "id", id, "error", err)
		writeError(w, http.StatusInternalServerError, "failed to start environment")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// Stop stops a running environment.
func (h *EnvironmentHandler) Stop(w http.ResponseWriter, r *http.Request) {
	id, err := parseUUID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid environment id")
		return
	}

	if err := h.service.Stop(r.Context(), id); err != nil {
		h.logger.Error("stop environment", "id", id, "error", err)
		writeError(w, http.StatusInternalServerError, "failed to stop environment")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// Remove deletes an environment and its container.
func (h *EnvironmentHandler) Remove(w http.ResponseWriter, r *http.Request) {
	id, err := parseUUID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid environment id")
		return
	}

	if err := h.service.Remove(r.Context(), id); err != nil {
		h.logger.Error("remove environment", "id", id, "error", err)
		writeError(w, http.StatusInternalServerError, "failed to remove environment")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// Logs streams container logs via Server-Sent Events.
func (h *EnvironmentHandler) Logs(w http.ResponseWriter, r *http.Request) {
	id, err := parseUUID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid environment id")
		return
	}

	flusher, ok := w.(http.Flusher)
	if !ok {
		writeError(w, http.StatusInternalServerError, "streaming not supported")
		return
	}

	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	flusher.Flush()

	err = h.service.StreamLogs(r.Context(), id, func(data string) {
		fmt.Fprintf(w, "data: %s\n\n", data)
		flusher.Flush()
	})
	if err != nil {
		h.logger.Debug("log stream ended", "id", id, "error", err)
	}
}
