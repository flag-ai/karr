package bonnie

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

// Client defines operations available against a BONNIE agent.
type Client interface {
	// SystemInfo returns host system info.
	SystemInfo(ctx context.Context) (*SystemInfoResponse, error)
	// GPUStatus returns GPU snapshot.
	GPUStatus(ctx context.Context) (*GPUSnapshot, error)
	// ListContainers returns all containers on the host.
	ListContainers(ctx context.Context) ([]ContainerInfo, error)
	// CreateContainer creates a new container.
	CreateContainer(ctx context.Context, req *CreateContainerRequest) (string, error)
	// StartContainer starts a container.
	StartContainer(ctx context.Context, id string) error
	// StopContainer stops a container.
	StopContainer(ctx context.Context, id string) error
	// RestartContainer restarts a container.
	RestartContainer(ctx context.Context, id string) error
	// RemoveContainer removes a container.
	RemoveContainer(ctx context.Context, id string) error
	// StreamLogs streams container logs via SSE. The callback receives each log line.
	StreamLogs(ctx context.Context, id string, callback func(data string)) error
	// Health checks if the agent is reachable.
	Health(ctx context.Context) error
}

type httpClient struct {
	baseURL    string
	token      string
	httpClient *http.Client
}

// NewClient creates a new BONNIE HTTP client.
func NewClient(baseURL, token string) Client {
	return &httpClient{
		baseURL: baseURL,
		token:   token,
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
	}
}

func (c *httpClient) do(ctx context.Context, method, path string, body io.Reader) (*http.Response, error) {
	url := c.baseURL + path

	var lastErr error
	for attempt := 0; attempt < 3; attempt++ {
		req, err := http.NewRequestWithContext(ctx, method, url, body)
		if err != nil {
			return nil, fmt.Errorf("bonnie: create request: %w", err)
		}
		req.Header.Set("Content-Type", "application/json")
		if c.token != "" {
			req.Header.Set("Authorization", "Bearer "+c.token)
		}

		resp, err := c.httpClient.Do(req)
		if err != nil {
			lastErr = err
			// Exponential backoff: 500ms, 1s, 2s
			select {
			case <-ctx.Done():
				return nil, ctx.Err()
			case <-time.After(time.Duration(500<<uint(attempt)) * time.Millisecond):
			}
			continue
		}

		return resp, nil
	}
	return nil, fmt.Errorf("bonnie: request failed after 3 attempts: %w", lastErr)
}

func (c *httpClient) Health(ctx context.Context) error {
	resp, err := c.do(ctx, http.MethodGet, "/health", nil)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		return fmt.Errorf("bonnie: health check returned %d", resp.StatusCode)
	}
	return nil
}

func (c *httpClient) SystemInfo(ctx context.Context) (*SystemInfoResponse, error) {
	resp, err := c.do(ctx, http.MethodGet, "/api/v1/system/info", nil)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var result SystemInfoResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("bonnie: decode system info: %w", err)
	}
	return &result, nil
}

func (c *httpClient) GPUStatus(ctx context.Context) (*GPUSnapshot, error) {
	resp, err := c.do(ctx, http.MethodGet, "/api/v1/gpu/status", nil)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var result GPUSnapshot
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("bonnie: decode gpu status: %w", err)
	}
	return &result, nil
}

func (c *httpClient) ListContainers(ctx context.Context) ([]ContainerInfo, error) {
	resp, err := c.do(ctx, http.MethodGet, "/api/v1/containers", nil)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var result []ContainerInfo
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("bonnie: decode containers: %w", err)
	}
	return result, nil
}

func (c *httpClient) CreateContainer(ctx context.Context, req *CreateContainerRequest) (string, error) {
	body, err := json.Marshal(req)
	if err != nil {
		return "", fmt.Errorf("bonnie: marshal request: %w", err)
	}

	resp, err := c.do(ctx, http.MethodPost, "/api/v1/containers", bytes.NewReader(body))
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusCreated && resp.StatusCode != http.StatusOK {
		respBody, _ := io.ReadAll(resp.Body)
		return "", fmt.Errorf("bonnie: create container returned %d: %s", resp.StatusCode, string(respBody))
	}

	var result map[string]string
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return "", fmt.Errorf("bonnie: decode create response: %w", err)
	}
	return result["id"], nil
}

func (c *httpClient) containerAction(ctx context.Context, id, action string) error {
	resp, err := c.do(ctx, http.MethodPost, "/api/v1/containers/"+id+"/"+action, nil)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		respBody, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("bonnie: %s container returned %d: %s", action, resp.StatusCode, string(respBody))
	}
	return nil
}

func (c *httpClient) StartContainer(ctx context.Context, id string) error {
	return c.containerAction(ctx, id, "start")
}

func (c *httpClient) StopContainer(ctx context.Context, id string) error {
	return c.containerAction(ctx, id, "stop")
}

func (c *httpClient) RestartContainer(ctx context.Context, id string) error {
	return c.containerAction(ctx, id, "restart")
}

func (c *httpClient) RemoveContainer(ctx context.Context, id string) error {
	resp, err := c.do(ctx, http.MethodDelete, "/api/v1/containers/"+id, nil)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		respBody, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("bonnie: remove container returned %d: %s", resp.StatusCode, string(respBody))
	}
	return nil
}

func (c *httpClient) StreamLogs(ctx context.Context, id string, callback func(data string)) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+"/api/v1/containers/"+id+"/logs", nil)
	if err != nil {
		return fmt.Errorf("bonnie: create log request: %w", err)
	}
	if c.token != "" {
		req.Header.Set("Authorization", "Bearer "+c.token)
	}
	req.Header.Set("Accept", "text/event-stream")

	// Use a client without timeout for streaming.
	streamClient := &http.Client{}
	resp, err := streamClient.Do(req)
	if err != nil {
		return fmt.Errorf("bonnie: log stream: %w", err)
	}
	defer resp.Body.Close()

	// Read SSE events.
	buf := make([]byte, 4096)
	for {
		n, readErr := resp.Body.Read(buf)
		if n > 0 {
			lines := strings.Split(string(buf[:n]), "\n")
			for _, line := range lines {
				if strings.HasPrefix(line, "data: ") {
					callback(strings.TrimPrefix(line, "data: "))
				}
			}
		}
		if readErr != nil {
			if readErr == io.EOF || ctx.Err() != nil {
				return nil
			}
			return readErr
		}
	}
}
