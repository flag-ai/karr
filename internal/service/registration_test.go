package service

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"testing"

	"github.com/flag-ai/karr/internal/bonnie"
	"github.com/flag-ai/karr/internal/db/sqlc"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgtype"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// regMockQuerier extends mockQuerier with registration-specific overrides.
type regMockQuerier struct {
	mockQuerier
	registrations               map[pgtype.UUID]sqlc.KarrAgentRegistration
	createAgentRegistrationFn   func(ctx context.Context, arg sqlc.CreateAgentRegistrationParams) (sqlc.KarrAgentRegistration, error)
	getPendingRegistrationFn    func(ctx context.Context, tokenHash string) (sqlc.KarrAgentRegistration, error)
	claimRegistrationFn         func(ctx context.Context, arg sqlc.ClaimRegistrationParams) error
	listRegistrationsFn         func(ctx context.Context) ([]sqlc.KarrAgentRegistration, error)
	deleteRegistrationFn        func(ctx context.Context, id pgtype.UUID) error
	cleanExpiredRegistrationsFn func(ctx context.Context) error
}

func newRegMockQuerier() *regMockQuerier {
	return &regMockQuerier{
		mockQuerier:   *newMockQuerier(),
		registrations: make(map[pgtype.UUID]sqlc.KarrAgentRegistration),
	}
}

func (m *regMockQuerier) CreateAgentRegistration(ctx context.Context, arg sqlc.CreateAgentRegistrationParams) (sqlc.KarrAgentRegistration, error) {
	if m.createAgentRegistrationFn != nil {
		return m.createAgentRegistrationFn(ctx, arg)
	}
	id := uuid.New()
	reg := sqlc.KarrAgentRegistration{
		ID:        toPgUUID(id),
		TokenHash: arg.TokenHash,
		Label:     arg.Label,
		Status:    "pending",
	}
	m.registrations[reg.ID] = reg
	return reg, nil
}

func (m *regMockQuerier) GetPendingRegistration(ctx context.Context, tokenHash string) (sqlc.KarrAgentRegistration, error) {
	if m.getPendingRegistrationFn != nil {
		return m.getPendingRegistrationFn(ctx, tokenHash)
	}
	for k := range m.registrations {
		if m.registrations[k].TokenHash == tokenHash && m.registrations[k].Status == "pending" {
			return m.registrations[k], nil
		}
	}
	return sqlc.KarrAgentRegistration{}, fmt.Errorf("not found")
}

func (m *regMockQuerier) ClaimRegistration(ctx context.Context, arg sqlc.ClaimRegistrationParams) error {
	if m.claimRegistrationFn != nil {
		return m.claimRegistrationFn(ctx, arg)
	}
	r, ok := m.registrations[arg.ID]
	if !ok {
		return fmt.Errorf("not found")
	}
	r.Status = "claimed"
	r.AgentID = arg.AgentID
	m.registrations[arg.ID] = r
	return nil
}

func (m *regMockQuerier) ListRegistrations(ctx context.Context) ([]sqlc.KarrAgentRegistration, error) {
	if m.listRegistrationsFn != nil {
		return m.listRegistrationsFn(ctx)
	}
	result := make([]sqlc.KarrAgentRegistration, 0, len(m.registrations))
	for k := range m.registrations {
		result = append(result, m.registrations[k])
	}
	return result, nil
}

func (m *regMockQuerier) DeleteRegistration(ctx context.Context, id pgtype.UUID) error {
	if m.deleteRegistrationFn != nil {
		return m.deleteRegistrationFn(ctx, id)
	}
	delete(m.registrations, id)
	return nil
}

func (m *regMockQuerier) CleanExpiredRegistrations(ctx context.Context) error {
	if m.cleanExpiredRegistrationsFn != nil {
		return m.cleanExpiredRegistrationsFn(ctx)
	}
	return nil
}

func TestRegistrationService_Provision(t *testing.T) {
	mq := newRegMockQuerier()
	reg := bonnie.NewRegistry(nil, testLogger())
	svc := NewRegistrationService(mq, reg, testLogger())
	ctx := context.Background()

	result, err := svc.Provision(ctx, "gpu-host-1", "https://karr.example.com")
	require.NoError(t, err)

	assert.NotEmpty(t, result.Token)
	assert.NotEqual(t, uuid.Nil, result.ID)
	assert.Contains(t, result.InstallCommand, "curl -fsSL")
	assert.Contains(t, result.InstallCommand, "https://karr.example.com/api/v1/install.sh")
	assert.Contains(t, result.InstallCommand, result.Token)

	// Token should be hex-encoded (64 chars for 32 bytes).
	assert.Len(t, result.Token, 64)

	// Verify the stored hash matches SHA-256 of the plaintext token.
	hash := sha256.Sum256([]byte(result.Token))
	expectedHash := hex.EncodeToString(hash[:])
	assert.Len(t, mq.registrations, 1)
	for _, r := range mq.registrations {
		assert.Equal(t, expectedHash, r.TokenHash)
		assert.Equal(t, "gpu-host-1", r.Label)
	}
}

func TestRegistrationService_Provision_EmptyLabel(t *testing.T) {
	mq := newRegMockQuerier()
	reg := bonnie.NewRegistry(nil, testLogger())
	svc := NewRegistrationService(mq, reg, testLogger())

	_, err := svc.Provision(context.Background(), "", "https://karr.example.com")
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "label is required")
}

func TestRegistrationService_Register(t *testing.T) {
	mq := newRegMockQuerier()
	registry := bonnie.NewRegistry(nil, testLogger())
	svc := NewRegistrationService(mq, registry, testLogger())
	ctx := context.Background()

	// Provision first to create a pending registration.
	result, err := svc.Provision(ctx, "gpu-host-1", "https://karr.example.com")
	require.NoError(t, err)

	// Register with the token.
	agent, err := svc.Register(ctx, result.Token, "192.168.1.100", 7777, "agent-auth-token", "")
	require.NoError(t, err)

	assert.Equal(t, "gpu-host-1", agent.Name)
	assert.Equal(t, "http://192.168.1.100:7777", agent.URL)
	assert.Empty(t, agent.Token, "token should be stripped from response")

	// Agent should be in the BONNIE registry.
	_, ok := registry.Get(agent.ID)
	assert.True(t, ok, "agent should be registered in BONNIE registry")

	// Registration should be claimed.
	for _, r := range mq.registrations {
		assert.Equal(t, "claimed", r.Status)
	}
}

func TestRegistrationService_Register_WithAddressOverride(t *testing.T) {
	mq := newRegMockQuerier()
	registry := bonnie.NewRegistry(nil, testLogger())
	svc := NewRegistrationService(mq, registry, testLogger())
	ctx := context.Background()

	result, err := svc.Provision(ctx, "gpu-host-2", "https://karr.example.com")
	require.NoError(t, err)

	agent, err := svc.Register(ctx, result.Token, "10.0.0.1", 7777, "auth", "192.168.50.10")
	require.NoError(t, err)

	// Should use the address override, not the source IP.
	assert.Equal(t, "http://192.168.50.10:7777", agent.URL)
}

func TestRegistrationService_Register_InvalidToken(t *testing.T) {
	mq := newRegMockQuerier()
	registry := bonnie.NewRegistry(nil, testLogger())
	svc := NewRegistrationService(mq, registry, testLogger())

	_, err := svc.Register(context.Background(), "nonexistent-token", "192.168.1.1", 7777, "auth", "")
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "invalid or expired")
}

func TestRegistrationService_List(t *testing.T) {
	mq := newRegMockQuerier()
	registry := bonnie.NewRegistry(nil, testLogger())
	svc := NewRegistrationService(mq, registry, testLogger())
	ctx := context.Background()

	// Provision two registrations.
	_, err := svc.Provision(ctx, "host-1", "https://karr.example.com")
	require.NoError(t, err)
	_, err = svc.Provision(ctx, "host-2", "https://karr.example.com")
	require.NoError(t, err)

	regs, err := svc.List(ctx)
	require.NoError(t, err)
	assert.Len(t, regs, 2)
}

func TestRegistrationService_Delete(t *testing.T) {
	mq := newRegMockQuerier()
	registry := bonnie.NewRegistry(nil, testLogger())
	svc := NewRegistrationService(mq, registry, testLogger())
	ctx := context.Background()

	result, err := svc.Provision(ctx, "host-1", "https://karr.example.com")
	require.NoError(t, err)

	err = svc.Delete(ctx, result.ID)
	require.NoError(t, err)

	regs, err := svc.List(ctx)
	require.NoError(t, err)
	assert.Len(t, regs, 0)
}
