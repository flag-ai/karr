// Package config provides KARR-specific configuration loading.
package config

import (
	"context"
	"fmt"
	"log/slog"

	"github.com/flag-ai/commons/config"
	"github.com/flag-ai/commons/logging"
	"github.com/flag-ai/commons/secrets"
)

// Config holds all KARR configuration, embedding the commons Base config.
type Config struct {
	config.Base

	// DefaultAgentURL is the default BONNIE agent URL to register on startup.
	DefaultAgentURL string

	// DefaultAgentToken is the bearer token for the default BONNIE agent.
	DefaultAgentToken string
}

// Load builds a KARR Config by reading environment variables via the secrets provider.
func Load(ctx context.Context, provider secrets.Provider) (*Config, error) {
	if provider == nil {
		return nil, fmt.Errorf("config: secrets provider is required")
	}

	base, err := config.LoadBase(ctx, "karr", provider)
	if err != nil {
		return nil, err
	}

	return &Config{
		Base:              *base,
		DefaultAgentURL:   provider.GetOrDefault(ctx, "KARR_DEFAULT_AGENT_URL", ""),
		DefaultAgentToken: provider.GetOrDefault(ctx, "KARR_DEFAULT_AGENT_TOKEN", ""),
	}, nil
}

// Logger creates a configured logger from the config.
func (c *Config) Logger() *slog.Logger {
	return logging.New(c.Component,
		logging.WithLevel(logging.ParseLevel(c.LogLevel)),
		logging.WithFormat(logging.Format(c.LogFormat)),
	)
}
