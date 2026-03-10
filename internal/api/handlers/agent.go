package handlers

import (
	"log/slog"
	"net/http"

	"github.com/flag-ai/karr/internal/service"
)

// AgentHandler serves agent-related HTTP endpoints.
type AgentHandler struct {
	service service.AgentServicer
	logger  *slog.Logger
}

// NewAgentHandler creates an AgentHandler.
func NewAgentHandler(svc service.AgentServicer, logger *slog.Logger) *AgentHandler {
	return &AgentHandler{
		service: svc,
		logger:  logger,
	}
}

// List returns all registered agents.
func (h *AgentHandler) List(w http.ResponseWriter, r *http.Request) {
	agents, err := h.service.List(r.Context())
	if err != nil {
		h.logger.Error("list agents", "error", err)
		writeError(w, http.StatusInternalServerError, "failed to list agents")
		return
	}
	writeJSON(w, http.StatusOK, agents)
}

// Get returns a single agent by ID.
func (h *AgentHandler) Get(w http.ResponseWriter, r *http.Request) {
	id, err := parseUUID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid agent id")
		return
	}

	agent, err := h.service.Get(r.Context(), id)
	if err != nil {
		h.logger.Error("get agent", "id", id, "error", err)
		writeError(w, http.StatusNotFound, "agent not found")
		return
	}
	writeJSON(w, http.StatusOK, agent)
}

// Create registers a new agent.
func (h *AgentHandler) Create(w http.ResponseWriter, r *http.Request) {
	var req service.CreateAgentInput
	if err := decodeBody(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}

	if req.Name == "" || req.URL == "" {
		writeError(w, http.StatusBadRequest, "name and url are required")
		return
	}

	agent, err := h.service.Create(r.Context(), req)
	if err != nil {
		h.logger.Error("create agent", "error", err)
		writeError(w, http.StatusInternalServerError, "failed to create agent")
		return
	}
	writeJSON(w, http.StatusCreated, agent)
}

// Delete removes an agent by ID.
func (h *AgentHandler) Delete(w http.ResponseWriter, r *http.Request) {
	id, err := parseUUID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid agent id")
		return
	}

	if err := h.service.Delete(r.Context(), id); err != nil {
		h.logger.Error("delete agent", "id", id, "error", err)
		writeError(w, http.StatusInternalServerError, "failed to delete agent")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// GetStatus returns the live status of an agent.
func (h *AgentHandler) GetStatus(w http.ResponseWriter, r *http.Request) {
	id, err := parseUUID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid agent id")
		return
	}

	status, err := h.service.GetStatus(r.Context(), id)
	if err != nil {
		h.logger.Error("get agent status", "id", id, "error", err)
		writeError(w, http.StatusNotFound, "agent not found")
		return
	}
	writeJSON(w, http.StatusOK, status)
}
