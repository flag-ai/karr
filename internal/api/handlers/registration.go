package handlers

import (
	"log/slog"
	"net/http"

	"github.com/flag-ai/karr/internal/service"
)

// ProvisionRequest is the JSON body for provisioning a registration token.
type ProvisionRequest struct {
	Label string `json:"label"`
}

// RegistrationHandler serves registration-related HTTP endpoints.
type RegistrationHandler struct {
	service service.RegistrationServicer
	logger  *slog.Logger
}

// NewRegistrationHandler creates a RegistrationHandler.
func NewRegistrationHandler(svc service.RegistrationServicer, logger *slog.Logger) *RegistrationHandler {
	return &RegistrationHandler{
		service: svc,
		logger:  logger,
	}
}

// Provision generates an install command with a one-time registration token.
func (h *RegistrationHandler) Provision(w http.ResponseWriter, r *http.Request) {
	var req ProvisionRequest
	if err := decodeBody(w, r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}

	if req.Label == "" {
		writeError(w, http.StatusBadRequest, "label is required")
		return
	}

	// Determine the server URL for the install command.
	serverURL := detectServerURL(r)

	result, err := h.service.Provision(r.Context(), req.Label, serverURL)
	if err != nil {
		h.logger.Error("provision agent", "error", err)
		writeError(w, http.StatusInternalServerError, "failed to provision agent")
		return
	}
	writeJSON(w, http.StatusCreated, result)
}

// List returns all registration records.
func (h *RegistrationHandler) List(w http.ResponseWriter, r *http.Request) {
	regs, err := h.service.List(r.Context())
	if err != nil {
		h.logger.Error("list registrations", "error", err)
		writeError(w, http.StatusInternalServerError, "failed to list registrations")
		return
	}
	writeJSON(w, http.StatusOK, regs)
}

// Delete removes a registration record.
func (h *RegistrationHandler) Delete(w http.ResponseWriter, r *http.Request) {
	id, err := parseUUID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid registration id")
		return
	}

	if err := h.service.Delete(r.Context(), id); err != nil {
		h.logger.Error("delete registration", "id", id, "error", err)
		writeError(w, http.StatusInternalServerError, "failed to delete registration")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// detectServerURL auto-detects the server base URL from request headers.
// Only accepts "http" or "https" as the scheme from X-Forwarded-Proto.
func detectServerURL(r *http.Request) string {
	scheme := "http"
	if proto := r.Header.Get("X-Forwarded-Proto"); proto == "https" {
		scheme = "https"
	} else if r.TLS != nil {
		scheme = "https"
	}
	return scheme + "://" + r.Host
}
