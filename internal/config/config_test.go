package config_test

import (
	"context"
	"fmt"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/flag-ai/karr/internal/config"
)

type mockProvider struct {
	values map[string]string
}

func (m *mockProvider) Get(_ context.Context, key string) (string, error) {
	v, ok := m.values[key]
	if !ok {
		return "", fmt.Errorf("key %q not found", key)
	}
	return v, nil
}

func (m *mockProvider) GetOrDefault(_ context.Context, key, defaultVal string) string {
	v, ok := m.values[key]
	if !ok {
		return defaultVal
	}
	return v
}

func TestLoad_Defaults(t *testing.T) {
	provider := &mockProvider{values: map[string]string{
		"DATABASE_URL": "postgres://localhost/karr",
	}}

	cfg, err := config.Load(context.Background(), provider)
	require.NoError(t, err)

	assert.Equal(t, "karr", cfg.Component)
	assert.Equal(t, "info", cfg.LogLevel)
	assert.Equal(t, "text", cfg.LogFormat)
	assert.Equal(t, ":8080", cfg.ListenAddr)
	assert.Equal(t, "postgres://localhost/karr", cfg.DatabaseURL)
	assert.Empty(t, cfg.DefaultAgentURL)
	assert.Empty(t, cfg.DefaultAgentToken)
}

func TestLoad_CustomValues(t *testing.T) {
	provider := &mockProvider{values: map[string]string{
		"DATABASE_URL":             "postgres://db:5432/karr",
		"LOG_LEVEL":                "debug",
		"LOG_FORMAT":               "json",
		"LISTEN_ADDR":              ":9090",
		"KARR_DEFAULT_AGENT_URL":   "http://gpu-host:7777",
		"KARR_DEFAULT_AGENT_TOKEN": "secret-token",
	}}

	cfg, err := config.Load(context.Background(), provider)
	require.NoError(t, err)

	assert.Equal(t, "debug", cfg.LogLevel)
	assert.Equal(t, "json", cfg.LogFormat)
	assert.Equal(t, ":9090", cfg.ListenAddr)
	assert.Equal(t, "http://gpu-host:7777", cfg.DefaultAgentURL)
	assert.Equal(t, "secret-token", cfg.DefaultAgentToken)
}

func TestLoad_MissingDatabaseURL(t *testing.T) {
	provider := &mockProvider{values: map[string]string{}}

	_, err := config.Load(context.Background(), provider)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "DATABASE_URL")
}

func TestLoad_NilProvider(t *testing.T) {
	_, err := config.Load(context.Background(), nil)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "secrets provider is required")
}

func TestConfig_Logger(t *testing.T) {
	provider := &mockProvider{values: map[string]string{
		"DATABASE_URL": "postgres://localhost/karr",
	}}

	cfg, err := config.Load(context.Background(), provider)
	require.NoError(t, err)

	logger := cfg.Logger()
	assert.NotNil(t, logger)
}
