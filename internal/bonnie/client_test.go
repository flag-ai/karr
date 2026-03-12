package bonnie

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func newTestServer(t *testing.T) (*httptest.Server, *http.ServeMux) {
	t.Helper()
	mux := http.NewServeMux()
	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)
	return srv, mux
}

func TestHealth_Success(t *testing.T) {
	srv, mux := newTestServer(t)
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = fmt.Fprintln(w, `{"status":"ok"}`)
	})

	c := NewClient(srv.URL, "test-token")
	err := c.Health(context.Background())
	assert.NoError(t, err)
}

func TestHealth_Error(t *testing.T) {
	srv, mux := newTestServer(t)
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
	})

	c := NewClient(srv.URL, "test-token")
	err := c.Health(context.Background())
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "503")
}

func TestSystemInfo(t *testing.T) {
	srv, mux := newTestServer(t)
	expected := SystemInfoResponse{
		System: SystemInfo{
			Hostname: "gpu-node-1",
			OS:       "linux",
			Arch:     "amd64",
			Kernel:   "6.1.0",
			CPUModel: "AMD EPYC 7763",
			CPUCores: 64,
			MemoryMB: 131072,
		},
		Disk: DiskUsage{
			TotalGB:     1000,
			UsedGB:      400,
			AvailableGB: 600,
			UsedPercent: "40%",
		},
	}
	mux.HandleFunc("/api/v1/system/info", func(w http.ResponseWriter, r *http.Request) {
		assert.Equal(t, http.MethodGet, r.Method)
		assert.Equal(t, "Bearer test-token", r.Header.Get("Authorization"))
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(expected)
	})

	c := NewClient(srv.URL, "test-token")
	result, err := c.SystemInfo(context.Background())
	require.NoError(t, err)
	assert.Equal(t, expected.System.Hostname, result.System.Hostname)
	assert.Equal(t, expected.System.CPUCores, result.System.CPUCores)
	assert.Equal(t, expected.Disk.TotalGB, result.Disk.TotalGB)
}

func TestGPUStatus(t *testing.T) {
	srv, mux := newTestServer(t)
	ts := time.Now().Truncate(time.Second)
	expected := GPUSnapshot{
		Vendor: GPUVendorNVIDIA,
		GPUs: []GPUInfo{
			{
				Index:       0,
				Name:        "RTX 4090",
				Vendor:      GPUVendorNVIDIA,
				MemoryTotal: 24576,
				MemoryFree:  20000,
				Utilization: 15,
			},
		},
		Timestamp: ts,
	}
	mux.HandleFunc("/api/v1/gpu/status", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(expected)
	})

	c := NewClient(srv.URL, "test-token")
	result, err := c.GPUStatus(context.Background())
	require.NoError(t, err)
	assert.Equal(t, GPUVendorNVIDIA, result.Vendor)
	require.Len(t, result.GPUs, 1)
	assert.Equal(t, "RTX 4090", result.GPUs[0].Name)
	assert.Equal(t, uint64(24576), result.GPUs[0].MemoryTotal)
}

func TestListContainers(t *testing.T) {
	srv, mux := newTestServer(t)
	expected := []ContainerInfo{
		{
			ID:      "abc123",
			Name:    "ollama-server",
			Image:   "ollama/ollama:latest",
			State:   "running",
			Status:  "Up 2 hours",
			Created: time.Now().Unix(),
		},
		{
			ID:      "def456",
			Name:    "vllm-server",
			Image:   "vllm/vllm:latest",
			State:   "exited",
			Status:  "Exited (0) 1 hour ago",
			Created: time.Now().Unix(),
		},
	}
	mux.HandleFunc("/api/v1/containers", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			w.WriteHeader(http.StatusMethodNotAllowed)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(expected)
	})

	c := NewClient(srv.URL, "test-token")
	result, err := c.ListContainers(context.Background())
	require.NoError(t, err)
	require.Len(t, result, 2)
	assert.Equal(t, "abc123", result[0].ID)
	assert.Equal(t, "ollama-server", result[0].Name)
	assert.Equal(t, "exited", result[1].State)
}

func TestCreateContainer(t *testing.T) {
	srv, mux := newTestServer(t)
	mux.HandleFunc("/api/v1/containers", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			w.WriteHeader(http.StatusMethodNotAllowed)
			return
		}
		var req CreateContainerRequest
		err := json.NewDecoder(r.Body).Decode(&req)
		if err != nil {
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		assert.Equal(t, "test-container", req.Name)
		assert.Equal(t, "ubuntu:latest", req.Image)
		assert.True(t, req.GPU)

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusCreated)
		_ = json.NewEncoder(w).Encode(map[string]string{"id": "new-container-id"})
	})

	c := NewClient(srv.URL, "test-token")
	id, err := c.CreateContainer(context.Background(), &CreateContainerRequest{
		Name:  "test-container",
		Image: "ubuntu:latest",
		GPU:   true,
		Env:   []string{"FOO=bar"},
	})
	require.NoError(t, err)
	assert.Equal(t, "new-container-id", id)
}

func TestStartContainer(t *testing.T) {
	srv, mux := newTestServer(t)
	mux.HandleFunc("/api/v1/containers/abc123/start", func(w http.ResponseWriter, r *http.Request) {
		assert.Equal(t, http.MethodPost, r.Method)
		w.WriteHeader(http.StatusOK)
	})

	c := NewClient(srv.URL, "test-token")
	err := c.StartContainer(context.Background(), "abc123")
	assert.NoError(t, err)
}

func TestStopContainer(t *testing.T) {
	srv, mux := newTestServer(t)
	mux.HandleFunc("/api/v1/containers/abc123/stop", func(w http.ResponseWriter, r *http.Request) {
		assert.Equal(t, http.MethodPost, r.Method)
		w.WriteHeader(http.StatusOK)
	})

	c := NewClient(srv.URL, "test-token")
	err := c.StopContainer(context.Background(), "abc123")
	assert.NoError(t, err)
}

func TestRemoveContainer(t *testing.T) {
	srv, mux := newTestServer(t)
	mux.HandleFunc("/api/v1/containers/abc123", func(w http.ResponseWriter, r *http.Request) {
		assert.Equal(t, http.MethodDelete, r.Method)
		w.WriteHeader(http.StatusOK)
	})

	c := NewClient(srv.URL, "test-token")
	err := c.RemoveContainer(context.Background(), "abc123")
	assert.NoError(t, err)
}

func TestStreamLogs(t *testing.T) {
	srv, mux := newTestServer(t)
	mux.HandleFunc("/api/v1/containers/abc123/logs", func(w http.ResponseWriter, r *http.Request) {
		assert.Equal(t, "text/event-stream", r.Header.Get("Accept"))
		w.Header().Set("Content-Type", "text/event-stream")
		flusher, ok := w.(http.Flusher)
		if !ok {
			t.Fatal("expected flusher")
		}
		for i := 0; i < 3; i++ {
			_, _ = fmt.Fprintf(w, "data: log line %d\n\n", i)
			flusher.Flush()
		}
	})

	c := NewClient(srv.URL, "test-token")
	var mu sync.Mutex
	var lines []string
	err := c.StreamLogs(context.Background(), "abc123", func(data string) {
		mu.Lock()
		defer mu.Unlock()
		lines = append(lines, data)
	})
	require.NoError(t, err)

	mu.Lock()
	defer mu.Unlock()
	assert.GreaterOrEqual(t, len(lines), 3)
	assert.Equal(t, "log line 0", lines[0])
	assert.Equal(t, "log line 1", lines[1])
	assert.Equal(t, "log line 2", lines[2])
}

func TestRetryOnError(t *testing.T) {
	var mu sync.Mutex
	attempts := 0

	srv, mux := newTestServer(t)
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		attempts++
		current := attempts
		mu.Unlock()

		if current < 3 {
			// Close the connection to simulate network error.
			hj, ok := w.(http.Hijacker)
			if !ok {
				t.Fatal("expected hijacker")
			}
			conn, _, err := hj.Hijack()
			if err != nil {
				t.Fatal(err)
			}
			_ = conn.Close()
			return
		}
		w.WriteHeader(http.StatusOK)
	})

	c := NewClient(srv.URL, "test-token")
	err := c.Health(context.Background())
	assert.NoError(t, err)

	mu.Lock()
	assert.Equal(t, 3, attempts)
	mu.Unlock()
}
