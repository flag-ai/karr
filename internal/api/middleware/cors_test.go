package middleware_test

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/flag-ai/karr/internal/api/middleware"
	"github.com/stretchr/testify/assert"
)

func TestCORS_SetsHeaders(t *testing.T) {
	handler := middleware.CORS()(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))

	req := httptest.NewRequest(http.MethodGet, "/", http.NoBody)
	rr := httptest.NewRecorder()

	handler.ServeHTTP(rr, req)

	assert.Equal(t, http.StatusOK, rr.Code)
	assert.Equal(t, "*", rr.Header().Get("Access-Control-Allow-Origin"))
	assert.Contains(t, rr.Header().Get("Access-Control-Allow-Methods"), "GET")
	assert.Contains(t, rr.Header().Get("Access-Control-Allow-Methods"), "POST")
	assert.Contains(t, rr.Header().Get("Access-Control-Allow-Headers"), "Content-Type")
}

func TestCORS_Preflight(t *testing.T) {
	called := false
	handler := middleware.CORS()(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		called = true
	}))

	req := httptest.NewRequest(http.MethodOptions, "/api/v1/agents", http.NoBody)
	rr := httptest.NewRecorder()

	handler.ServeHTTP(rr, req)

	assert.Equal(t, http.StatusNoContent, rr.Code)
	assert.False(t, called, "OPTIONS should not reach the next handler")
	assert.Equal(t, "*", rr.Header().Get("Access-Control-Allow-Origin"))
}
