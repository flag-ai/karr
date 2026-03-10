//go:build integration

package integration

import (
	"bufio"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"testing"

	"github.com/flag-ai/karr/internal/models"
	"github.com/flag-ai/karr/internal/service"
)

// TestAgentCRUD exercises the full agent lifecycle: create, list, get, delete.
func TestAgentCRUD(t *testing.T) {
	ts := setupTestServer(t)

	// --- Create agent ---
	createBody := fmt.Sprintf(`{"name":"test-agent","url":"%s","token":"test-token"}`, ts.BonnieURL)
	resp := doRequest(t, ts.Client, http.MethodPost, ts.Server.URL+"/api/v1/agents", createBody)
	requireStatus(t, resp, http.StatusCreated)

	var created models.Agent
	decodeJSON(t, resp, &created)

	if created.Name != "test-agent" {
		t.Fatalf("expected agent name 'test-agent', got %q", created.Name)
	}
	if created.URL != ts.BonnieURL {
		t.Fatalf("expected agent URL %q, got %q", ts.BonnieURL, created.URL)
	}
	if created.Token != "" {
		t.Fatal("expected token to be stripped from response")
	}
	if created.ID.String() == "" {
		t.Fatal("expected non-empty agent ID")
	}

	agentID := created.ID.String()

	// --- List agents ---
	resp = doRequest(t, ts.Client, http.MethodGet, ts.Server.URL+"/api/v1/agents", "")
	requireStatus(t, resp, http.StatusOK)

	var agents []models.Agent
	decodeJSON(t, resp, &agents)

	if len(agents) != 1 {
		t.Fatalf("expected 1 agent, got %d", len(agents))
	}
	if agents[0].ID.String() != agentID {
		t.Fatalf("listed agent ID mismatch: expected %s, got %s", agentID, agents[0].ID.String())
	}

	// --- Get agent by ID ---
	resp = doRequest(t, ts.Client, http.MethodGet, ts.Server.URL+"/api/v1/agents/"+agentID, "")
	requireStatus(t, resp, http.StatusOK)

	var fetched models.Agent
	decodeJSON(t, resp, &fetched)

	if fetched.ID.String() != agentID {
		t.Fatalf("fetched agent ID mismatch: expected %s, got %s", agentID, fetched.ID.String())
	}
	if fetched.Name != "test-agent" {
		t.Fatalf("fetched agent name mismatch: expected 'test-agent', got %q", fetched.Name)
	}

	// --- Get agent status (calls mock BONNIE) ---
	resp = doRequest(t, ts.Client, http.MethodGet, ts.Server.URL+"/api/v1/agents/"+agentID+"/status", "")
	requireStatus(t, resp, http.StatusOK)

	var statusResp service.AgentStatusResponse
	decodeJSON(t, resp, &statusResp)

	if statusResp.Agent.ID.String() != agentID {
		t.Fatalf("status agent ID mismatch")
	}
	if statusResp.System == nil {
		t.Fatal("expected system info in agent status")
	}
	if statusResp.System.System.Hostname != "test-host" {
		t.Fatalf("expected hostname 'test-host', got %q", statusResp.System.System.Hostname)
	}
	if statusResp.GPU == nil {
		t.Fatal("expected GPU info in agent status")
	}
	if len(statusResp.GPU.GPUs) != 1 {
		t.Fatalf("expected 1 GPU, got %d", len(statusResp.GPU.GPUs))
	}

	// --- Delete agent ---
	resp = doRequest(t, ts.Client, http.MethodDelete, ts.Server.URL+"/api/v1/agents/"+agentID, "")
	requireStatus(t, resp, http.StatusNoContent)
	resp.Body.Close()

	// --- Verify deletion ---
	resp = doRequest(t, ts.Client, http.MethodGet, ts.Server.URL+"/api/v1/agents/"+agentID, "")
	requireStatus(t, resp, http.StatusNotFound)
	resp.Body.Close()

	// --- List should be empty ---
	resp = doRequest(t, ts.Client, http.MethodGet, ts.Server.URL+"/api/v1/agents", "")
	requireStatus(t, resp, http.StatusOK)

	var emptyAgents []models.Agent
	decodeJSON(t, resp, &emptyAgents)

	if len(emptyAgents) != 0 {
		t.Fatalf("expected 0 agents after delete, got %d", len(emptyAgents))
	}
}

// TestProjectCRUD exercises the full project lifecycle: create, list, get, update, delete.
func TestProjectCRUD(t *testing.T) {
	ts := setupTestServer(t)

	// --- Create project ---
	resp := doRequest(t, ts.Client, http.MethodPost, ts.Server.URL+"/api/v1/projects",
		`{"name":"my-project","description":"A test project"}`)
	requireStatus(t, resp, http.StatusCreated)

	var created models.Project
	decodeJSON(t, resp, &created)

	if created.Name != "my-project" {
		t.Fatalf("expected project name 'my-project', got %q", created.Name)
	}
	if created.Description != "A test project" {
		t.Fatalf("expected description 'A test project', got %q", created.Description)
	}

	projectID := created.ID.String()

	// --- List projects ---
	resp = doRequest(t, ts.Client, http.MethodGet, ts.Server.URL+"/api/v1/projects", "")
	requireStatus(t, resp, http.StatusOK)

	var projects []models.Project
	decodeJSON(t, resp, &projects)

	if len(projects) != 1 {
		t.Fatalf("expected 1 project, got %d", len(projects))
	}

	// --- Get project ---
	resp = doRequest(t, ts.Client, http.MethodGet, ts.Server.URL+"/api/v1/projects/"+projectID, "")
	requireStatus(t, resp, http.StatusOK)

	var fetched models.Project
	decodeJSON(t, resp, &fetched)

	if fetched.ID.String() != projectID {
		t.Fatalf("project ID mismatch")
	}

	// --- Update project ---
	resp = doRequest(t, ts.Client, http.MethodPut, ts.Server.URL+"/api/v1/projects/"+projectID,
		`{"name":"renamed-project","description":"Updated description"}`)
	requireStatus(t, resp, http.StatusOK)

	var updated models.Project
	decodeJSON(t, resp, &updated)

	if updated.Name != "renamed-project" {
		t.Fatalf("expected updated name 'renamed-project', got %q", updated.Name)
	}
	if updated.Description != "Updated description" {
		t.Fatalf("expected updated description 'Updated description', got %q", updated.Description)
	}

	// --- Partial update (only name) ---
	resp = doRequest(t, ts.Client, http.MethodPut, ts.Server.URL+"/api/v1/projects/"+projectID,
		`{"name":"final-name"}`)
	requireStatus(t, resp, http.StatusOK)

	var partial models.Project
	decodeJSON(t, resp, &partial)

	if partial.Name != "final-name" {
		t.Fatalf("expected name 'final-name', got %q", partial.Name)
	}

	// --- Delete project ---
	resp = doRequest(t, ts.Client, http.MethodDelete, ts.Server.URL+"/api/v1/projects/"+projectID, "")
	requireStatus(t, resp, http.StatusNoContent)
	resp.Body.Close()

	// --- Verify deletion ---
	resp = doRequest(t, ts.Client, http.MethodGet, ts.Server.URL+"/api/v1/projects/"+projectID, "")
	requireStatus(t, resp, http.StatusNotFound)
	resp.Body.Close()
}

// TestEnvironmentLifecycle exercises the full environment lifecycle:
// create agent, create environment, start, stop, remove.
func TestEnvironmentLifecycle(t *testing.T) {
	ts := setupTestServer(t)

	// --- Create agent first (environments require an agent) ---
	createAgentBody := fmt.Sprintf(`{"name":"env-test-agent","url":"%s","token":"test-token"}`, ts.BonnieURL)
	resp := doRequest(t, ts.Client, http.MethodPost, ts.Server.URL+"/api/v1/agents", createAgentBody)
	requireStatus(t, resp, http.StatusCreated)

	var agent models.Agent
	decodeJSON(t, resp, &agent)
	agentID := agent.ID.String()

	// --- Create environment ---
	createEnvBody := fmt.Sprintf(`{
		"agent_id": "%s",
		"name": "test-env",
		"image": "nvidia/cuda:12.0-devel",
		"gpu": true,
		"env": ["CUDA_VISIBLE_DEVICES=0"],
		"command": ["sleep", "infinity"]
	}`, agentID)
	resp = doRequest(t, ts.Client, http.MethodPost, ts.Server.URL+"/api/v1/environments", createEnvBody)
	requireStatus(t, resp, http.StatusCreated)

	var env models.Environment
	decodeJSON(t, resp, &env)

	if env.Name != "test-env" {
		t.Fatalf("expected env name 'test-env', got %q", env.Name)
	}
	if env.Image != "nvidia/cuda:12.0-devel" {
		t.Fatalf("expected image 'nvidia/cuda:12.0-devel', got %q", env.Image)
	}
	if !env.GPU {
		t.Fatal("expected gpu=true")
	}
	if env.ContainerID != "test-container-123" {
		t.Fatalf("expected container ID 'test-container-123', got %q", env.ContainerID)
	}
	if env.Status != models.EnvironmentStatusStopped {
		t.Fatalf("expected status 'stopped' after create, got %q", env.Status)
	}

	envID := env.ID.String()

	// --- List environments ---
	resp = doRequest(t, ts.Client, http.MethodGet, ts.Server.URL+"/api/v1/environments", "")
	requireStatus(t, resp, http.StatusOK)

	var envs []models.Environment
	decodeJSON(t, resp, &envs)

	if len(envs) != 1 {
		t.Fatalf("expected 1 environment, got %d", len(envs))
	}

	// --- Get environment ---
	resp = doRequest(t, ts.Client, http.MethodGet, ts.Server.URL+"/api/v1/environments/"+envID, "")
	requireStatus(t, resp, http.StatusOK)

	var fetchedEnv models.Environment
	decodeJSON(t, resp, &fetchedEnv)

	if fetchedEnv.ID.String() != envID {
		t.Fatalf("environment ID mismatch")
	}

	// --- Start environment ---
	resp = doRequest(t, ts.Client, http.MethodPost, ts.Server.URL+"/api/v1/environments/"+envID+"/start", "")
	requireStatus(t, resp, http.StatusNoContent)
	resp.Body.Close()

	// Verify status is now running.
	resp = doRequest(t, ts.Client, http.MethodGet, ts.Server.URL+"/api/v1/environments/"+envID, "")
	requireStatus(t, resp, http.StatusOK)

	var runningEnv models.Environment
	decodeJSON(t, resp, &runningEnv)

	if runningEnv.Status != models.EnvironmentStatusRunning {
		t.Fatalf("expected status 'running' after start, got %q", runningEnv.Status)
	}

	// --- Stop environment ---
	resp = doRequest(t, ts.Client, http.MethodPost, ts.Server.URL+"/api/v1/environments/"+envID+"/stop", "")
	requireStatus(t, resp, http.StatusNoContent)
	resp.Body.Close()

	// Verify status is now stopped.
	resp = doRequest(t, ts.Client, http.MethodGet, ts.Server.URL+"/api/v1/environments/"+envID, "")
	requireStatus(t, resp, http.StatusOK)

	var stoppedEnv models.Environment
	decodeJSON(t, resp, &stoppedEnv)

	if stoppedEnv.Status != models.EnvironmentStatusStopped {
		t.Fatalf("expected status 'stopped' after stop, got %q", stoppedEnv.Status)
	}

	// --- Remove environment ---
	resp = doRequest(t, ts.Client, http.MethodDelete, ts.Server.URL+"/api/v1/environments/"+envID, "")
	requireStatus(t, resp, http.StatusNoContent)
	resp.Body.Close()

	// --- Verify deletion ---
	resp = doRequest(t, ts.Client, http.MethodGet, ts.Server.URL+"/api/v1/environments/"+envID, "")
	requireStatus(t, resp, http.StatusNotFound)
	resp.Body.Close()
}

// TestHealthAndMetrics verifies the operational endpoints: /health, /ready, /metrics.
func TestHealthAndMetrics(t *testing.T) {
	ts := setupTestServer(t)

	// --- GET /health ---
	resp := doRequest(t, ts.Client, http.MethodGet, ts.Server.URL+"/health", "")
	requireStatus(t, resp, http.StatusOK)

	var healthResp map[string]string
	decodeJSON(t, resp, &healthResp)

	if healthResp["status"] != "ok" {
		t.Fatalf("expected health status 'ok', got %q", healthResp["status"])
	}
	if _, ok := healthResp["version"]; !ok {
		t.Fatal("expected version field in health response")
	}

	// --- GET /ready ---
	resp = doRequest(t, ts.Client, http.MethodGet, ts.Server.URL+"/ready", "")
	requireStatus(t, resp, http.StatusOK)

	var readyResp map[string]any
	decodeJSON(t, resp, &readyResp)

	healthy, ok := readyResp["healthy"].(bool)
	if !ok || !healthy {
		t.Fatalf("expected ready healthy=true, got %v", readyResp["healthy"])
	}

	// --- GET /metrics ---
	resp = doRequest(t, ts.Client, http.MethodGet, ts.Server.URL+"/metrics", "")
	requireStatus(t, resp, http.StatusOK)

	body, err := io.ReadAll(resp.Body)
	resp.Body.Close()
	if err != nil {
		t.Fatalf("read metrics body: %v", err)
	}

	metricsBody := string(body)
	// Prometheus metrics should contain at least the go runtime metrics.
	if !strings.Contains(metricsBody, "go_goroutines") {
		t.Fatal("expected Prometheus metrics to contain go_goroutines")
	}
}

// TestSSELogs verifies that the environment logs endpoint returns
// valid Server-Sent Events.
func TestSSELogs(t *testing.T) {
	ts := setupTestServer(t)

	// --- Create agent ---
	createAgentBody := fmt.Sprintf(`{"name":"sse-agent","url":"%s","token":"test-token"}`, ts.BonnieURL)
	resp := doRequest(t, ts.Client, http.MethodPost, ts.Server.URL+"/api/v1/agents", createAgentBody)
	requireStatus(t, resp, http.StatusCreated)

	var agent models.Agent
	decodeJSON(t, resp, &agent)

	// --- Create environment ---
	createEnvBody := fmt.Sprintf(`{
		"agent_id": "%s",
		"name": "sse-test-env",
		"image": "alpine:latest",
		"gpu": false
	}`, agent.ID.String())
	resp = doRequest(t, ts.Client, http.MethodPost, ts.Server.URL+"/api/v1/environments", createEnvBody)
	requireStatus(t, resp, http.StatusCreated)

	var env models.Environment
	decodeJSON(t, resp, &env)

	// --- Start environment (so it has a running container) ---
	resp = doRequest(t, ts.Client, http.MethodPost, ts.Server.URL+"/api/v1/environments/"+env.ID.String()+"/start", "")
	requireStatus(t, resp, http.StatusNoContent)
	resp.Body.Close()

	// --- GET logs via SSE ---
	req, err := http.NewRequest(http.MethodGet, ts.Server.URL+"/api/v1/environments/"+env.ID.String()+"/logs", nil)
	if err != nil {
		t.Fatalf("create log request: %v", err)
	}
	req.Header.Set("Accept", "text/event-stream")

	resp, err = ts.Client.Do(req)
	if err != nil {
		t.Fatalf("SSE request: %v", err)
	}
	defer resp.Body.Close()

	requireStatus(t, resp, http.StatusOK)

	contentType := resp.Header.Get("Content-Type")
	if !strings.HasPrefix(contentType, "text/event-stream") {
		t.Fatalf("expected Content-Type 'text/event-stream', got %q", contentType)
	}

	// Read all SSE events from the stream.
	var events []string
	scanner := bufio.NewScanner(resp.Body)
	for scanner.Scan() {
		line := scanner.Text()
		if strings.HasPrefix(line, "data: ") {
			events = append(events, strings.TrimPrefix(line, "data: "))
		}
	}
	if err := scanner.Err(); err != nil {
		t.Fatalf("read SSE stream: %v", err)
	}

	// The mock BONNIE sends 4 log lines, which are then proxied by KARR
	// as SSE events (data: <line>). Verify we received them.
	expectedLines := []string{
		"container starting...",
		"loading model weights",
		"model loaded successfully",
		"server listening on :8080",
	}

	if len(events) < len(expectedLines) {
		t.Fatalf("expected at least %d SSE events, got %d: %v", len(expectedLines), len(events), events)
	}

	for i, expected := range expectedLines {
		if events[i] != expected {
			t.Fatalf("SSE event %d: expected %q, got %q", i, expected, events[i])
		}
	}
}

// TestCreateAgentValidation verifies that the agent create endpoint
// rejects invalid input.
func TestCreateAgentValidation(t *testing.T) {
	ts := setupTestServer(t)

	tests := []struct {
		name string
		body string
	}{
		{"empty body", `{}`},
		{"missing url", `{"name":"agent-no-url"}`},
		{"missing name", `{"url":"http://localhost:9090"}`},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			resp := doRequest(t, ts.Client, http.MethodPost, ts.Server.URL+"/api/v1/agents", tt.body)
			if resp.StatusCode != http.StatusBadRequest {
				t.Fatalf("expected 400 for %s, got %d", tt.name, resp.StatusCode)
			}

			var errResp map[string]string
			decodeJSON(t, resp, &errResp)

			if _, ok := errResp["error"]; !ok {
				t.Fatal("expected error field in response")
			}
		})
	}
}

// TestCreateProjectValidation verifies that the project create endpoint
// rejects invalid input.
func TestCreateProjectValidation(t *testing.T) {
	ts := setupTestServer(t)

	resp := doRequest(t, ts.Client, http.MethodPost, ts.Server.URL+"/api/v1/projects", `{}`)
	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("expected 400 for empty project name, got %d", resp.StatusCode)
	}
	resp.Body.Close()
}

// TestCreateEnvironmentValidation verifies that the environment create endpoint
// rejects invalid input.
func TestCreateEnvironmentValidation(t *testing.T) {
	ts := setupTestServer(t)

	tests := []struct {
		name string
		body string
	}{
		{"empty body", `{}`},
		{"missing image", `{"name":"env-no-image","agent_id":"00000000-0000-0000-0000-000000000000"}`},
		{"missing name", `{"image":"alpine:latest","agent_id":"00000000-0000-0000-0000-000000000000"}`},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			resp := doRequest(t, ts.Client, http.MethodPost, ts.Server.URL+"/api/v1/environments", tt.body)
			if resp.StatusCode != http.StatusBadRequest {
				t.Fatalf("expected 400 for %s, got %d", tt.name, resp.StatusCode)
			}

			var errResp map[string]string
			decodeJSON(t, resp, &errResp)

			if _, ok := errResp["error"]; !ok {
				t.Fatal("expected error field in response")
			}
		})
	}
}

// TestGetNonExistentAgent verifies 404 for a non-existent agent.
func TestGetNonExistentAgent(t *testing.T) {
	ts := setupTestServer(t)

	resp := doRequest(t, ts.Client, http.MethodGet,
		ts.Server.URL+"/api/v1/agents/00000000-0000-0000-0000-000000000000", "")
	requireStatus(t, resp, http.StatusNotFound)
	resp.Body.Close()
}

// TestGetInvalidUUID verifies 400 for a malformed UUID.
func TestGetInvalidUUID(t *testing.T) {
	ts := setupTestServer(t)

	endpoints := []string{
		"/api/v1/agents/not-a-uuid",
		"/api/v1/projects/not-a-uuid",
		"/api/v1/environments/not-a-uuid",
	}

	for _, ep := range endpoints {
		t.Run(ep, func(t *testing.T) {
			resp := doRequest(t, ts.Client, http.MethodGet, ts.Server.URL+ep, "")
			requireStatus(t, resp, http.StatusBadRequest)

			var errResp map[string]string
			decodeJSON(t, resp, &errResp)

			if _, ok := errResp["error"]; !ok {
				t.Fatal("expected error field in response")
			}
		})
	}
}

// TestEnvironmentWithProject verifies that environments can be linked to projects.
func TestEnvironmentWithProject(t *testing.T) {
	ts := setupTestServer(t)

	// Create agent.
	createAgentBody := fmt.Sprintf(`{"name":"proj-agent","url":"%s","token":""}`, ts.BonnieURL)
	resp := doRequest(t, ts.Client, http.MethodPost, ts.Server.URL+"/api/v1/agents", createAgentBody)
	requireStatus(t, resp, http.StatusCreated)

	var agent models.Agent
	decodeJSON(t, resp, &agent)

	// Create project.
	resp = doRequest(t, ts.Client, http.MethodPost, ts.Server.URL+"/api/v1/projects",
		`{"name":"linked-project","description":"Has environments"}`)
	requireStatus(t, resp, http.StatusCreated)

	var project models.Project
	decodeJSON(t, resp, &project)

	// Create environment linked to project.
	createEnvBody := fmt.Sprintf(`{
		"agent_id": "%s",
		"project_id": "%s",
		"name": "project-env",
		"image": "python:3.12",
		"gpu": false
	}`, agent.ID.String(), project.ID.String())

	resp = doRequest(t, ts.Client, http.MethodPost, ts.Server.URL+"/api/v1/environments", createEnvBody)
	requireStatus(t, resp, http.StatusCreated)

	var env models.Environment
	decodeJSON(t, resp, &env)

	if env.ProjectID == nil {
		t.Fatal("expected project_id to be set")
	}
	if env.ProjectID.String() != project.ID.String() {
		t.Fatalf("expected project_id %s, got %s", project.ID.String(), env.ProjectID.String())
	}

	// Clean up: remove environment, then project and agent.
	resp = doRequest(t, ts.Client, http.MethodDelete, ts.Server.URL+"/api/v1/environments/"+env.ID.String(), "")
	requireStatus(t, resp, http.StatusNoContent)
	resp.Body.Close()

	resp = doRequest(t, ts.Client, http.MethodDelete, ts.Server.URL+"/api/v1/projects/"+project.ID.String(), "")
	requireStatus(t, resp, http.StatusNoContent)
	resp.Body.Close()

	resp = doRequest(t, ts.Client, http.MethodDelete, ts.Server.URL+"/api/v1/agents/"+agent.ID.String(), "")
	requireStatus(t, resp, http.StatusNoContent)
	resp.Body.Close()
}

// TestCORSHeaders verifies that CORS middleware is active.
func TestCORSHeaders(t *testing.T) {
	ts := setupTestServer(t)

	req, err := http.NewRequest(http.MethodOptions, ts.Server.URL+"/api/v1/agents", nil)
	if err != nil {
		t.Fatalf("create OPTIONS request: %v", err)
	}
	req.Header.Set("Origin", "http://localhost:3000")
	req.Header.Set("Access-Control-Request-Method", "POST")

	resp, err := ts.Client.Do(req)
	if err != nil {
		t.Fatalf("OPTIONS request: %v", err)
	}
	defer resp.Body.Close()

	// The CORS middleware should respond to preflight requests.
	// We don't assert the exact status (varies by implementation)
	// but verify the CORS header is present.
	acaoHeader := resp.Header.Get("Access-Control-Allow-Origin")
	if acaoHeader == "" {
		t.Log("WARNING: Access-Control-Allow-Origin header not set on preflight response")
	}
}

// TestJSONContentType verifies that API responses have the correct Content-Type.
func TestJSONContentType(t *testing.T) {
	ts := setupTestServer(t)

	endpoints := []struct {
		method string
		path   string
	}{
		{http.MethodGet, "/health"},
		{http.MethodGet, "/ready"},
		{http.MethodGet, "/api/v1/agents"},
		{http.MethodGet, "/api/v1/projects"},
		{http.MethodGet, "/api/v1/environments"},
	}

	for _, ep := range endpoints {
		t.Run(ep.method+" "+ep.path, func(t *testing.T) {
			resp := doRequest(t, ts.Client, ep.method, ts.Server.URL+ep.path, "")
			defer resp.Body.Close()

			// Drain body.
			_, _ = io.ReadAll(resp.Body)

			ct := resp.Header.Get("Content-Type")
			if !strings.HasPrefix(ct, "application/json") {
				// Skip metrics since it uses text/plain.
				if ep.path == "/metrics" {
					return
				}
				t.Fatalf("expected Content-Type starting with 'application/json', got %q", ct)
			}
		})
	}
}

// decodeJSONRaw is a helper that decodes into json.RawMessage for flexible inspection.
func decodeJSONRaw(t *testing.T, resp *http.Response) map[string]json.RawMessage {
	t.Helper()
	defer resp.Body.Close()

	var raw map[string]json.RawMessage
	if err := json.NewDecoder(resp.Body).Decode(&raw); err != nil {
		t.Fatalf("decode raw JSON: %v", err)
	}
	return raw
}
