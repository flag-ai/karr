package handlers_test

import (
	"context"
	"errors"
	"testing"

	"github.com/stretchr/testify/assert"

	"github.com/flag-ai/karr/internal/api/handlers"
)

type mockAgentAvailability struct {
	err error
}

func (m *mockAgentAvailability) HasOnlineAgent(_ context.Context) error {
	return m.err
}

func TestBonnieChecker_Name(t *testing.T) {
	t.Parallel()
	checker := handlers.NewBonnieChecker(&mockAgentAvailability{})
	assert.Equal(t, "bonnie-agents", checker.Name())
}

func TestBonnieChecker_Check_Online(t *testing.T) {
	t.Parallel()
	checker := handlers.NewBonnieChecker(&mockAgentAvailability{err: nil})
	assert.NoError(t, checker.Check(context.Background()))
}

func TestBonnieChecker_Check_NoAgents(t *testing.T) {
	t.Parallel()
	checker := handlers.NewBonnieChecker(&mockAgentAvailability{
		err: errors.New("no agents registered"),
	})
	err := checker.Check(context.Background())
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "no agents registered")
}

func TestBonnieChecker_Check_AllOffline(t *testing.T) {
	t.Parallel()
	checker := handlers.NewBonnieChecker(&mockAgentAvailability{
		err: errors.New("no online agents (2 registered, all offline)"),
	})
	err := checker.Check(context.Background())
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "all offline")
}
