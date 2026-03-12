package api

import (
	"io/fs"
	"net/http"
	"strings"
)

// SPAHandler serves the embedded SPA files, falling back to index.html
// for unmatched routes so that client-side routing works.
func SPAHandler(spaFS fs.FS) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if spaFS == nil {
			http.NotFound(w, r)
			return
		}

		path := strings.TrimPrefix(r.URL.Path, "/")
		if path == "" {
			path = "index.html"
		}

		// Try to serve the file directly.
		f, err := spaFS.Open(path)
		if err != nil {
			// File not found — serve index.html for SPA routing.
			path = "index.html"
		} else {
			_ = f.Close()
		}

		http.ServeFileFS(w, r, spaFS, path)
	}
}
