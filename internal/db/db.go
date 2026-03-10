// Package db provides database connectivity for KARR.
package db

import (
	"context"
	"log/slog"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/flag-ai/commons/database"
)

// NewPool creates a new PostgreSQL connection pool.
func NewPool(ctx context.Context, connStr string, logger *slog.Logger) (*pgxpool.Pool, error) {
	return database.NewPool(ctx, connStr, database.WithPoolLogger(logger))
}

// RunMigrations executes database migrations from the given source path.
func RunMigrations(sourcePath, dbURL string, logger *slog.Logger) error {
	return database.RunMigrations(sourcePath, dbURL, logger)
}
