//go:build integration

package integration

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/flag-ai/commons/health"

	"github.com/flag-ai/karr/internal/api"
	"github.com/flag-ai/karr/internal/bonnie"
	"github.com/flag-ai/karr/internal/db"
	"github.com/flag-ai/karr/internal/db/sqlc"
	"github.com/flag-ai/karr/internal/service"
)

// newMockBONNIE creates an httptest.Server that implements the BONNIE agent API.
// The returned server is automatically closed when the test finishes.
func newMockBONNIE(t *testing.T) *httptest.Server {
	t.Helper()

	mux := http.NewServeMux()

	// GET /health
	mux.HandleFunc("GET /health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode(map[string]bool{"healthy": true})
	})

	// GET /api/v1/gpu/status
	mux.HandleFunc("GET /api/v1/gpu/status", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode(bonnie.GPUSnapshot{
			Vendor: bonnie.GPUVendorNVIDIA,
			GPUs: []bonnie.GPUInfo{
				{
					Index:       0,
					Name:        "NVIDIA RTX 4090",
					Vendor:      bonnie.GPUVendorNVIDIA,
					MemoryTotal: 24576,
					MemoryFree:  20480,
					Utilization: 15,
				},
			},
			Timestamp: time.Now().UTC(),
		})
	})

	// GET /api/v1/system/info
	mux.HandleFunc("GET /api/v1/system/info", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode(bonnie.SystemInfoResponse{
			System: bonnie.SystemInfo{
				Hostname: "test-host",
				OS:       "linux",
				Arch:     "amd64",
				Kernel:   "6.19.0",
				CPUModel: "AMD Ryzen 9 7950X",
				CPUCores: 32,
				MemoryMB: 131072,
			},
			Disk: bonnie.DiskUsage{
				TotalGB:     2000,
				UsedGB:      500,
				AvailableGB: 1500,
				UsedPercent: "25%",
			},
		})
	})

	// GET /api/v1/containers
	mux.HandleFunc("GET /api/v1/containers", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode([]bonnie.ContainerInfo{})
	})

	// POST /api/v1/containers
	mux.HandleFunc("POST /api/v1/containers", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusCreated)
		_ = json.NewEncoder(w).Encode(map[string]string{"id": "test-container-123"})
	})

	// POST /api/v1/containers/{id}/start
	mux.HandleFunc("POST /api/v1/containers/{id}/start", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode(map[string]string{"status": "started"})
	})

	// POST /api/v1/containers/{id}/stop
	mux.HandleFunc("POST /api/v1/containers/{id}/stop", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode(map[string]string{"status": "stopped"})
	})

	// DELETE /api/v1/containers/{id}
	mux.HandleFunc("DELETE /api/v1/containers/{id}", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNoContent)
	})

	// GET /api/v1/containers/{id}/logs — SSE stream
	mux.HandleFunc("GET /api/v1/containers/{id}/logs", func(w http.ResponseWriter, r *http.Request) {
		flusher, ok := w.(http.Flusher)
		if !ok {
			http.Error(w, "streaming not supported", http.StatusInternalServerError)
			return
		}

		w.Header().Set("Content-Type", "text/event-stream")
		w.Header().Set("Cache-Control", "no-cache")
		w.Header().Set("Connection", "keep-alive")
		w.WriteHeader(http.StatusOK)
		flusher.Flush()

		lines := []string{
			"container starting...",
			"loading model weights",
			"model loaded successfully",
			"server listening on :8080",
		}
		for _, line := range lines {
			fmt.Fprintf(w, "data: %s\n\n", line)
			flusher.Flush()
		}
	})

	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)
	return srv
}

// testServer holds all resources needed for an integration test.
type testServer struct {
	// Server is the KARR API httptest server.
	Server *httptest.Server
	// Client is pre-configured to talk to the KARR API.
	Client *http.Client
	// BonnieURL is the mock BONNIE agent's base URL.
	BonnieURL string
}

// setupTestServer creates a full KARR server backed by a real PostgreSQL
// database and a mock BONNIE agent. It runs migrations, registers the mock
// agent, and returns an HTTP client for making API requests.
//
// The test is skipped if TEST_DATABASE_URL is not set.
func setupTestServer(t *testing.T) *testServer {
	t.Helper()

	dbURL := os.Getenv("TEST_DATABASE_URL")
	if dbURL == "" {
		t.Skip("TEST_DATABASE_URL not set, skipping integration test")
	}

	ctx := context.Background()
	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelDebug}))

	// Run migrations.
	migrationsPath := findMigrationsPath(t)
	if err := db.RunMigrations(migrationsPath, dbURL, logger); err != nil {
		t.Fatalf("run migrations: %v", err)
	}

	// Create database pool.
	pool, err := db.NewPool(ctx, dbURL, logger)
	if err != nil {
		t.Fatalf("create db pool: %v", err)
	}
	t.Cleanup(pool.Close)

	// Clean tables before each test for isolation.
	cleanTables(t, ctx, pool)

	// sqlc queries.
	queries := sqlc.New(pool)

	// Start mock BONNIE agent.
	mockBonnie := newMockBONNIE(t)

	// BONNIE registry — use the mock URL for all agent clients.
	registry := bonnie.NewRegistry(queries, logger)

	// Services.
	agentSvc := service.NewAgentService(queries, registry, logger)
	projectSvc := service.NewProjectService(queries, logger)
	envSvc := service.NewEnvironmentService(queries, registry, logger)

	// Health registry (with DB checker).
	healthRegistry := health.NewRegistry()
	healthRegistry.Register(health.NewDatabaseChecker(pool))

	// Build router.
	router := api.NewRouter(&api.RouterConfig{
		Logger:             logger,
		HealthRegistry:     healthRegistry,
		AgentService:       agentSvc,
		ProjectService:     projectSvc,
		EnvironmentService: envSvc,
	})

	// Start KARR test server.
	karrServer := httptest.NewServer(router)
	t.Cleanup(karrServer.Close)

	return &testServer{
		Server:    karrServer,
		Client:    karrServer.Client(),
		BonnieURL: mockBonnie.URL,
	}
}

// cleanTables truncates all KARR tables for test isolation.
func cleanTables(t *testing.T, ctx context.Context, pool *pgxpool.Pool) {
	t.Helper()

	_, err := pool.Exec(ctx, "TRUNCATE karr_environments, karr_projects, karr_agents CASCADE")
	if err != nil {
		t.Fatalf("truncate tables: %v", err)
	}
}

// findMigrationsPath locates the migrations directory relative to the project root.
func findMigrationsPath(t *testing.T) string {
	t.Helper()

	// Walk up from the test file to find the migrations directory.
	candidates := []string{
		"migrations",
		"../../migrations",
		"../../../migrations",
	}
	for _, c := range candidates {
		abs, err := filepath.Abs(c)
		if err != nil {
			continue
		}
		if info, err := os.Stat(abs); err == nil && info.IsDir() {
			return "file://" + abs
		}
	}

	t.Fatal("could not find migrations directory")
	return ""
}

// doRequest is a convenience helper for making JSON API requests to the test server.
func doRequest(t *testing.T, client *http.Client, method, url, body string) *http.Response {
	t.Helper()

	var req *http.Request
	var err error
	if body != "" {
		req, err = http.NewRequest(method, url, strings.NewReader(body))
	} else {
		req, err = http.NewRequest(method, url, nil)
	}
	if err != nil {
		t.Fatalf("create request: %v", err)
	}

	if body != "" {
		req.Header.Set("Content-Type", "application/json")
	}

	resp, err := client.Do(req)
	if err != nil {
		t.Fatalf("%s %s: %v", method, url, err)
	}
	return resp
}

// decodeJSON decodes a JSON response body into dst.
func decodeJSON(t *testing.T, resp *http.Response, dst any) {
	t.Helper()
	defer resp.Body.Close()
	if err := json.NewDecoder(resp.Body).Decode(dst); err != nil {
		t.Fatalf("decode response: %v", err)
	}
}

// requireStatus asserts the response has the expected status code.
func requireStatus(t *testing.T, resp *http.Response, expected int) {
	t.Helper()
	if resp.StatusCode != expected {
		t.Fatalf("expected status %d, got %d", expected, resp.StatusCode)
	}
}
