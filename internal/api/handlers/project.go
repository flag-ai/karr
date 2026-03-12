package handlers

import (
	"log/slog"
	"net/http"

	"github.com/flag-ai/karr/internal/service"
)

// ProjectHandler serves project-related HTTP endpoints.
type ProjectHandler struct {
	service service.ProjectServicer
	logger  *slog.Logger
}

// NewProjectHandler creates a ProjectHandler.
func NewProjectHandler(svc service.ProjectServicer, logger *slog.Logger) *ProjectHandler {
	return &ProjectHandler{
		service: svc,
		logger:  logger,
	}
}

// List returns all projects.
func (h *ProjectHandler) List(w http.ResponseWriter, r *http.Request) {
	projects, err := h.service.List(r.Context())
	if err != nil {
		h.logger.Error("list projects", "error", err)
		writeError(w, http.StatusInternalServerError, "failed to list projects")
		return
	}
	writeJSON(w, http.StatusOK, projects)
}

// Get returns a single project by ID.
func (h *ProjectHandler) Get(w http.ResponseWriter, r *http.Request) {
	id, err := parseUUID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid project id")
		return
	}

	project, err := h.service.Get(r.Context(), id)
	if err != nil {
		if isNotFound(err) {
			writeError(w, http.StatusNotFound, "project not found")
			return
		}
		h.logger.Error("get project", "id", id, "error", err)
		writeError(w, http.StatusInternalServerError, "failed to get project")
		return
	}
	writeJSON(w, http.StatusOK, project)
}

// Create adds a new project.
func (h *ProjectHandler) Create(w http.ResponseWriter, r *http.Request) {
	var req service.CreateProjectInput
	if err := decodeBody(w, r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}

	if req.Name == "" {
		writeError(w, http.StatusBadRequest, "name is required")
		return
	}

	project, err := h.service.Create(r.Context(), req)
	if err != nil {
		h.logger.Error("create project", "error", err)
		writeError(w, http.StatusInternalServerError, "failed to create project")
		return
	}
	writeJSON(w, http.StatusCreated, project)
}

// Update modifies an existing project.
func (h *ProjectHandler) Update(w http.ResponseWriter, r *http.Request) {
	id, err := parseUUID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid project id")
		return
	}

	var req service.UpdateProjectInput
	if err := decodeBody(w, r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}

	project, err := h.service.Update(r.Context(), id, req)
	if err != nil {
		if isNotFound(err) {
			writeError(w, http.StatusNotFound, "project not found")
			return
		}
		h.logger.Error("update project", "id", id, "error", err)
		writeError(w, http.StatusInternalServerError, "failed to update project")
		return
	}
	writeJSON(w, http.StatusOK, project)
}

// Delete removes a project by ID.
func (h *ProjectHandler) Delete(w http.ResponseWriter, r *http.Request) {
	id, err := parseUUID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid project id")
		return
	}

	if err := h.service.Delete(r.Context(), id); err != nil {
		h.logger.Error("delete project", "id", id, "error", err)
		writeError(w, http.StatusInternalServerError, "failed to delete project")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}
