package middleware

import (
	"net/http"
	"strings"
)

// CORS returns middleware that sets CORS headers restricted to the given origins.
// If no origins are provided, CORS headers are omitted entirely (same-origin only).
// Pass a comma-separated string like "http://localhost:5173,http://localhost:8080".
func CORS(allowedOrigins string) func(http.Handler) http.Handler {
	origins := parseOrigins(allowedOrigins)

	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if len(origins) > 0 {
				reqOrigin := r.Header.Get("Origin")
				if allowed := matchOrigin(reqOrigin, origins); allowed != "" {
					w.Header().Set("Access-Control-Allow-Origin", allowed)
					w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
					w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")
					w.Header().Set("Vary", "Origin")
				}
			}

			if r.Method == http.MethodOptions {
				w.WriteHeader(http.StatusNoContent)
				return
			}

			next.ServeHTTP(w, r)
		})
	}
}

func parseOrigins(s string) []string {
	if s == "" {
		return nil
	}
	parts := strings.Split(s, ",")
	origins := make([]string, 0, len(parts))
	for _, p := range parts {
		if trimmed := strings.TrimSpace(p); trimmed != "" {
			origins = append(origins, trimmed)
		}
	}
	return origins
}

func matchOrigin(reqOrigin string, allowed []string) string {
	for _, o := range allowed {
		if o == reqOrigin {
			return o
		}
	}
	return ""
}
