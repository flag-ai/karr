package db_test

import (
	"context"
	"testing"

	"github.com/stretchr/testify/assert"

	"github.com/flag-ai/karr/internal/db"
)

func TestNewPool_InvalidConnectionString(t *testing.T) {
	_, err := db.NewPool(context.Background(), "not-a-valid-url", nil)
	assert.Error(t, err)
}

func TestRunMigrations_InvalidPath(t *testing.T) {
	err := db.RunMigrations("file:///nonexistent", "postgres://invalid", nil)
	assert.Error(t, err)
}
