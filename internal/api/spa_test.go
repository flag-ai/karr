package api_test

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"testing/fstest"

	"github.com/flag-ai/karr/internal/api"
	"github.com/stretchr/testify/assert"
)

func TestSPAHandler_NilFS(t *testing.T) {
	handler := api.SPAHandler(nil)

	req := httptest.NewRequest(http.MethodGet, "/", http.NoBody)
	rr := httptest.NewRecorder()

	handler.ServeHTTP(rr, req)

	assert.Equal(t, http.StatusNotFound, rr.Code)
}

func TestSPAHandler_ServesIndexHTML(t *testing.T) {
	fs := fstest.MapFS{
		"index.html": &fstest.MapFile{Data: []byte("<html>app</html>")},
	}

	handler := api.SPAHandler(fs)

	req := httptest.NewRequest(http.MethodGet, "/", http.NoBody)
	rr := httptest.NewRecorder()

	handler.ServeHTTP(rr, req)

	assert.Equal(t, http.StatusOK, rr.Code)
	assert.Contains(t, rr.Body.String(), "<html>app</html>")
}

func TestSPAHandler_ServesStaticFile(t *testing.T) {
	fs := fstest.MapFS{
		"index.html":       &fstest.MapFile{Data: []byte("<html>app</html>")},
		"assets/style.css": &fstest.MapFile{Data: []byte("body{}")},
	}

	handler := api.SPAHandler(fs)

	req := httptest.NewRequest(http.MethodGet, "/assets/style.css", http.NoBody)
	rr := httptest.NewRecorder()

	handler.ServeHTTP(rr, req)

	assert.Equal(t, http.StatusOK, rr.Code)
	assert.Contains(t, rr.Body.String(), "body{}")
}

func TestSPAHandler_FallbackToIndex(t *testing.T) {
	fs := fstest.MapFS{
		"index.html": &fstest.MapFile{Data: []byte("<html>app</html>")},
	}

	handler := api.SPAHandler(fs)

	// Client-side route that doesn't match a real file.
	req := httptest.NewRequest(http.MethodGet, "/dashboard/settings", http.NoBody)
	rr := httptest.NewRecorder()

	handler.ServeHTTP(rr, req)

	assert.Equal(t, http.StatusOK, rr.Code)
	assert.Contains(t, rr.Body.String(), "<html>app</html>")
}
