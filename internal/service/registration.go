package service

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"log/slog"
	"strings"
	"time"

	"github.com/flag-ai/karr/internal/bonnie"
	"github.com/flag-ai/karr/internal/db/sqlc"
	"github.com/flag-ai/karr/internal/models"
	"github.com/google/uuid"
)

// AgentRegistration is the domain model for a registration token record.
type AgentRegistration struct {
	ID        uuid.UUID  `json:"id"`
	Label     string     `json:"label"`
	Status    string     `json:"status"`
	AgentID   *uuid.UUID `json:"agent_id,omitempty"`
	CreatedAt time.Time  `json:"created_at"`
	ClaimedAt *time.Time `json:"claimed_at,omitempty"`
	ExpiresAt time.Time  `json:"expires_at"`
}

// ProvisionResult is the response from provisioning a registration token.
type ProvisionResult struct {
	ID             uuid.UUID `json:"id"`
	Token          string    `json:"token"`
	InstallCommand string    `json:"install_command"`
	ExpiresAt      time.Time `json:"expires_at"`
}

// RegistrationServicer defines the handler-facing interface for registration operations.
type RegistrationServicer interface {
	Provision(ctx context.Context, label, serverURL string) (ProvisionResult, error)
	Register(ctx context.Context, tokenPlain, sourceIP string, port int, authToken, address string) (models.Agent, error)
	List(ctx context.Context) ([]AgentRegistration, error)
	Delete(ctx context.Context, id uuid.UUID) error
}

// RegistrationService manages the agent install/registration flow.
type RegistrationService struct {
	queries  Querier
	registry *bonnie.Registry
	logger   *slog.Logger
}

// NewRegistrationService creates a RegistrationService.
func NewRegistrationService(queries Querier, registry *bonnie.Registry, logger *slog.Logger) *RegistrationService {
	return &RegistrationService{
		queries:  queries,
		registry: registry,
		logger:   logger,
	}
}

// Provision generates a one-time registration token and returns the install command.
func (s *RegistrationService) Provision(ctx context.Context, label, serverURL string) (ProvisionResult, error) {
	label = strings.TrimSpace(label)
	if label == "" {
		return ProvisionResult{}, fmt.Errorf("label is required")
	}

	// Clean up expired registrations while we're here.
	if err := s.queries.CleanExpiredRegistrations(ctx); err != nil {
		s.logger.Warn("failed to clean expired registrations", "error", err)
	}

	// Generate a random token.
	tokenBytes := make([]byte, 32)
	if _, err := rand.Read(tokenBytes); err != nil {
		return ProvisionResult{}, fmt.Errorf("generate token: %w", err)
	}
	tokenPlain := hex.EncodeToString(tokenBytes)

	// Store SHA-256 hash — never store plaintext.
	hash := sha256.Sum256([]byte(tokenPlain))
	tokenHash := hex.EncodeToString(hash[:])

	row, err := s.queries.CreateAgentRegistration(ctx, sqlc.CreateAgentRegistrationParams{
		TokenHash: tokenHash,
		Label:     label,
	})
	if err != nil {
		return ProvisionResult{}, fmt.Errorf("create registration: %w", err)
	}

	installCmd := fmt.Sprintf("curl -fsSL '%s/api/v1/install.sh?token=%s' | sudo bash", serverURL, tokenPlain)

	s.logger.Info("provisioned agent registration",
		slog.String("id", fromPgUUID(row.ID).String()),
		slog.String("label", label),
	)

	return ProvisionResult{
		ID:             fromPgUUID(row.ID),
		Token:          tokenPlain,
		InstallCommand: installCmd,
		ExpiresAt:      timeFromPgTimestamptz(row.ExpiresAt),
	}, nil
}

// Register validates a registration token, creates the agent, and claims the registration.
func (s *RegistrationService) Register(ctx context.Context, tokenPlain, sourceIP string, port int, authToken, address string) (models.Agent, error) {
	// Hash the incoming token to match against stored hash.
	hash := sha256.Sum256([]byte(tokenPlain))
	tokenHash := hex.EncodeToString(hash[:])

	reg, err := s.queries.GetPendingRegistration(ctx, tokenHash)
	if err != nil {
		return models.Agent{}, fmt.Errorf("invalid or expired registration token: %w", err)
	}

	// Determine agent address.
	agentAddr := sourceIP
	if address != "" {
		agentAddr = address
	}
	agentURL := fmt.Sprintf("http://%s:%d", agentAddr, port)

	// Use the label as the agent name.
	agentName := reg.Label
	if agentName == "" {
		agentName = agentAddr
	}

	// Create the agent record.
	agentRow, err := s.queries.CreateAgent(ctx, sqlc.CreateAgentParams{
		Name:   agentName,
		Url:    agentURL,
		Token:  authToken,
		Status: string(models.AgentStatusOffline),
	})
	if err != nil {
		return models.Agent{}, fmt.Errorf("create agent: %w", err)
	}

	agent := agentFromRow(agentRow)

	// Claim the registration.
	if err := s.queries.ClaimRegistration(ctx, sqlc.ClaimRegistrationParams{
		ID:      reg.ID,
		AgentID: agentRow.ID,
	}); err != nil {
		s.logger.Error("failed to claim registration", "error", err)
	}

	// Register with the BONNIE client registry for health monitoring.
	s.registry.Register(agent.ID, agent.Name, agentURL, authToken)

	s.logger.Info("agent registered via install script",
		slog.String("id", agent.ID.String()),
		slog.String("name", agent.Name),
		slog.String("url", agentURL),
	)

	agent.Token = "" // strip token from response
	return agent, nil
}

// List returns all registration records.
func (s *RegistrationService) List(ctx context.Context) ([]AgentRegistration, error) {
	// Clean up expired registrations.
	if err := s.queries.CleanExpiredRegistrations(ctx); err != nil {
		s.logger.Warn("failed to clean expired registrations", "error", err)
	}

	rows, err := s.queries.ListRegistrations(ctx)
	if err != nil {
		return nil, fmt.Errorf("list registrations: %w", err)
	}

	regs := make([]AgentRegistration, 0, len(rows))
	for i := range rows {
		r := registrationFromRow(rows[i])
		regs = append(regs, r)
	}
	return regs, nil
}

// Delete removes a registration record.
func (s *RegistrationService) Delete(ctx context.Context, id uuid.UUID) error {
	if err := s.queries.DeleteRegistration(ctx, toPgUUID(id)); err != nil {
		return fmt.Errorf("delete registration %s: %w", id, err)
	}
	return nil
}

// registrationFromRow converts a sqlc row to the domain model.
func registrationFromRow(row sqlc.KarrAgentRegistration) AgentRegistration { //nolint:gocritic // value receiver for clean conversion API
	reg := AgentRegistration{
		ID:        fromPgUUID(row.ID),
		Label:     row.Label,
		Status:    row.Status,
		CreatedAt: timeFromPgTimestamptz(row.CreatedAt),
		ClaimedAt: timePtrFromPgTimestamptz(row.ClaimedAt),
		ExpiresAt: timeFromPgTimestamptz(row.ExpiresAt),
	}
	if row.AgentID.Valid {
		aid := fromPgUUID(row.AgentID)
		reg.AgentID = &aid
	}
	return reg
}

// Compile-time check that RegistrationService satisfies RegistrationServicer.
var _ RegistrationServicer = (*RegistrationService)(nil)
