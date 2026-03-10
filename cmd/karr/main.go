// Package main is the entrypoint for the KARR server.
package main

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"github.com/flag-ai/commons/database"
	"github.com/flag-ai/commons/health"
	"github.com/flag-ai/commons/secrets"
	"github.com/flag-ai/commons/version"

	"github.com/flag-ai/karr/internal/api"
	"github.com/flag-ai/karr/internal/bonnie"
	"github.com/flag-ai/karr/internal/config"
	"github.com/flag-ai/karr/internal/db"
	"github.com/flag-ai/karr/internal/db/sqlc"
	"github.com/flag-ai/karr/internal/service"
)

func main() {
	if err := run(); err != nil {
		slog.Error("fatal", "error", err)
		os.Exit(1)
	}
}

func run() error {
	if len(os.Args) < 2 {
		fmt.Fprintf(os.Stderr, "Usage: karr <command>\n\nCommands:\n  serve     Start the KARR server\n  migrate   Run database migrations\n")
		os.Exit(1)
	}

	switch os.Args[1] {
	case "serve":
		return serve()
	case "migrate":
		return migrate()
	default:
		return fmt.Errorf("unknown command: %s", os.Args[1])
	}
}

func newProviderAndConfig(ctx context.Context) (*config.Config, *slog.Logger, error) {
	provider, err := secrets.NewProvider(secrets.ProviderOpenBao, nil)
	if err != nil {
		provider, _ = secrets.NewProvider(secrets.ProviderEnv, nil)
	}

	cfg, err := config.Load(ctx, provider)
	if err != nil {
		return nil, nil, err
	}

	logger := cfg.Logger()
	return cfg, logger, nil
}

func migrate() error {
	ctx := context.Background()
	cfg, logger, err := newProviderAndConfig(ctx)
	if err != nil {
		return err
	}

	if len(os.Args) < 3 || os.Args[2] != "up" {
		return fmt.Errorf("usage: karr migrate up")
	}

	logger.Info("running migrations")
	migrationsPath := migrationsSourcePath()
	return database.RunMigrations(migrationsPath, cfg.DatabaseURL, logger)
}

func serve() error {
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	cfg, logger, err := newProviderAndConfig(ctx)
	if err != nil {
		return err
	}

	logger.Info("starting karr", "version", version.Info(), "addr", cfg.ListenAddr)

	// Database pool
	pool, err := db.NewPool(ctx, cfg.DatabaseURL, logger)
	if err != nil {
		return err
	}
	defer pool.Close()

	// Run migrations
	migrationsPath := migrationsSourcePath()
	if err := db.RunMigrations(migrationsPath, cfg.DatabaseURL, logger); err != nil {
		return err
	}

	// sqlc queries
	queries := sqlc.New(pool)

	// BONNIE agent registry
	registry := bonnie.NewRegistry(queries, logger)
	if err := registry.LoadFromDB(ctx); err != nil {
		logger.Warn("failed to load agents from database", "error", err)
	}
	registry.StartHealthLoop(ctx)

	// Register default agent if configured
	if cfg.DefaultAgentURL != "" {
		if err := registry.EnsureDefault(ctx, cfg.DefaultAgentURL, cfg.DefaultAgentToken); err != nil {
			logger.Warn("failed to register default agent", "error", err)
		}
	}

	// Services
	agentSvc := service.NewAgentService(queries, registry, logger)
	projectSvc := service.NewProjectService(queries, logger)
	envSvc := service.NewEnvironmentService(queries, registry, logger)

	// Health registry
	healthRegistry := health.NewRegistry()
	healthRegistry.Register(health.NewDatabaseChecker(pool))

	// Build router
	router := api.NewRouter(&api.RouterConfig{
		Logger:             logger,
		HealthRegistry:     healthRegistry,
		AgentService:       agentSvc,
		ProjectService:     projectSvc,
		EnvironmentService: envSvc,
	})

	srv := &http.Server{
		Handler:           router,
		ReadHeaderTimeout: 10 * time.Second,
	}

	// Start server
	errCh := make(chan error, 1)
	go func() {
		ln, listenErr := net.Listen("tcp", cfg.ListenAddr)
		if listenErr != nil {
			errCh <- listenErr
			return
		}
		logger.Info("server listening", "addr", ln.Addr().String())
		if serveErr := srv.Serve(ln); serveErr != nil && !errors.Is(serveErr, http.ErrServerClosed) {
			errCh <- serveErr
		}
		close(errCh)
	}()

	// Wait for shutdown signal or server error
	select {
	case <-ctx.Done():
		logger.Info("shutdown signal received")
	case err := <-errCh:
		if err != nil {
			logger.Error("server error", "error", err)
		}
	}

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if err := srv.Shutdown(shutdownCtx); err != nil {
		return err
	}

	logger.Info("karr stopped")
	return nil
}

func migrationsSourcePath() string {
	// Check for migrations relative to the working directory first,
	// then fall back to the binary's location.
	if _, err := os.Stat("migrations"); err == nil {
		abs, _ := filepath.Abs("migrations")
		return "file://" + abs
	}
	exe, _ := os.Executable()
	return "file://" + filepath.Join(filepath.Dir(exe), "migrations")
}
