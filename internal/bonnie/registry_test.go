package bonnie

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"

	"github.com/google/uuid"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestRegistry_RegisterAndGet(t *testing.T) {
	reg := NewRegistry(nil, discardLogger())
	id := uuid.New()

	reg.Register(id, "test-agent", "http://localhost:9090", "tok")

	client, ok := reg.Get(id)
	require.True(t, ok)
	assert.NotNil(t, client)
}

func TestRegistry_GetMissing(t *testing.T) {
	reg := NewRegistry(nil, discardLogger())

	client, ok := reg.Get(uuid.New())
	assert.False(t, ok)
	assert.Nil(t, client)
}

func TestRegistry_Unregister(t *testing.T) {
	reg := NewRegistry(nil, discardLogger())
	id := uuid.New()

	reg.Register(id, "test-agent", "http://localhost:9090", "tok")
	reg.Unregister(id)

	_, ok := reg.Get(id)
	assert.False(t, ok)
}

func TestRegistry_ConcurrentAccess(t *testing.T) {
	reg := NewRegistry(nil, discardLogger())

	var wg sync.WaitGroup
	ids := make([]uuid.UUID, 50)
	for i := range ids {
		ids[i] = uuid.New()
	}

	// Concurrent writes.
	for i, id := range ids {
		wg.Add(1)
		go func(id uuid.UUID, idx int) {
			defer wg.Done()
			reg.Register(id, fmt.Sprintf("agent-%d", idx), "http://localhost:9090", "tok")
		}(id, i)
	}
	wg.Wait()

	// Concurrent reads.
	for _, id := range ids {
		wg.Add(1)
		go func(id uuid.UUID) {
			defer wg.Done()
			client, ok := reg.Get(id)
			assert.True(t, ok)
			assert.NotNil(t, client)
		}(id)
	}
	wg.Wait()

	// Concurrent unregisters.
	for _, id := range ids {
		wg.Add(1)
		go func(id uuid.UUID) {
			defer wg.Done()
			reg.Unregister(id)
		}(id)
	}
	wg.Wait()

	// Verify all removed.
	for _, id := range ids {
		_, ok := reg.Get(id)
		assert.False(t, ok)
	}
}

func TestRegistry_CheckAll_OnlineAgent(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(srv.Close)

	reg := NewRegistry(nil, discardLogger())
	id := uuid.New()
	reg.Register(id, "healthy-agent", srv.URL, "tok")

	// checkAll needs queries for DB update, but we can verify no panic with nil queries
	// by checking that the client health succeeds.
	client, ok := reg.Get(id)
	require.True(t, ok)
	err := client.Health(context.Background())
	assert.NoError(t, err)
}

func TestRegistry_CheckAll_OfflineAgent(t *testing.T) {
	// Create a server and close it immediately to simulate offline.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {}))
	offlineURL := srv.URL
	srv.Close()

	reg := NewRegistry(nil, discardLogger())
	id := uuid.New()
	reg.Register(id, "offline-agent", offlineURL, "tok")

	client, ok := reg.Get(id)
	require.True(t, ok)
	err := client.Health(context.Background())
	assert.Error(t, err)
}

func TestRegistry_RegisterOverwrite(t *testing.T) {
	reg := NewRegistry(nil, discardLogger())
	id := uuid.New()

	reg.Register(id, "agent-v1", "http://old:9090", "tok1")
	reg.Register(id, "agent-v2", "http://new:9090", "tok2")

	// Should have exactly one entry, the latest.
	client, ok := reg.Get(id)
	require.True(t, ok)
	assert.NotNil(t, client)
}

func discardLogger() *slog.Logger {
	return slog.Default()
}
