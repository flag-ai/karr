package handlers

import (
	"encoding/json"
	"errors"
	"net/http"

	"github.com/flag-ai/karr/internal/service"
	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
)

// isNotFound returns true if the error wraps service.ErrNotFound.
func isNotFound(err error) bool {
	return errors.Is(err, service.ErrNotFound)
}

// errorResponse is a standard error envelope.
type errorResponse struct {
	Error string `json:"error"`
}

// writeJSON writes v as JSON with the given status code.
func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

// writeError writes a JSON error response.
func writeError(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, errorResponse{Error: msg})
}

// parseUUID extracts and parses the "id" URL parameter.
func parseUUID(r *http.Request) (uuid.UUID, error) {
	raw := chi.URLParam(r, "id")
	return uuid.Parse(raw)
}

// decodeBody decodes the JSON request body into dst.
func decodeBody(r *http.Request, dst any) error {
	defer func() { _ = r.Body.Close() }()
	return json.NewDecoder(r.Body).Decode(dst)
}
