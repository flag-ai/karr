// Package api provides the HTTP API layer for the KARR server.
package api

import (
	"io/fs"
	"log/slog"

	"github.com/go-chi/chi/v5"

	"github.com/flag-ai/commons/health"
	"github.com/flag-ai/commons/install"
	"github.com/flag-ai/karr/internal/api/handlers"
	"github.com/flag-ai/karr/internal/api/middleware"
	"github.com/flag-ai/karr/internal/service"
)

// RouterConfig holds all dependencies needed to build the HTTP router.
type RouterConfig struct {
	Logger              *slog.Logger
	HealthRegistry      *health.Registry
	AgentService        service.AgentServicer
	ProjectService      service.ProjectServicer
	EnvironmentService  service.EnvironmentServicer
	RegistrationService service.RegistrationServicer
	InstallScriptCfg    *install.HandlerConfig // If nil, install.sh route is not registered.
	RegisterCallback    install.RegisterCallback
	SPAFS               fs.FS  // Embedded SPA filesystem (may be nil for API-only mode).
	CORSOrigins         string // Comma-separated allowed CORS origins.
}

// NewRouter builds a chi.Mux with all KARR routes registered.
func NewRouter(cfg *RouterConfig) *chi.Mux {
	r := chi.NewRouter()

	// Global middleware
	r.Use(middleware.Recovery(cfg.Logger))
	r.Use(middleware.SecurityHeaders())
	r.Use(middleware.Logging(cfg.Logger))
	r.Use(middleware.CORS(cfg.CORSOrigins))

	// Health endpoints (no auth)
	healthH := handlers.NewHealthHandler(cfg.HealthRegistry, cfg.Logger)
	r.Get("/health", healthH.Health)
	r.Get("/ready", healthH.Ready)

	// Metrics
	metricsH := handlers.NewMetricsHandler()
	r.Get("/metrics", metricsH.Metrics)

	// API v1 routes (no auth in Phase 1)
	r.Route("/api/v1", func(r chi.Router) {
		// Install script (no auth — token is in query string)
		if cfg.InstallScriptCfg != nil {
			r.Get("/install.sh", install.ScriptHandler(*cfg.InstallScriptCfg))
		}

		// Agent self-registration (no auth — token is in body)
		if cfg.RegisterCallback != nil {
			r.Post("/agents/register", install.RegisterHandler(cfg.RegisterCallback, cfg.Logger))
		}

		// Agent provisioning (registration management)
		if cfg.RegistrationService != nil {
			regH := handlers.NewRegistrationHandler(cfg.RegistrationService, cfg.Logger)
			r.Post("/agents/provision", regH.Provision)
			r.Get("/agents/registrations", regH.List)
			r.Delete("/agents/registrations/{id}", regH.Delete)
		}

		// Agents
		agentH := handlers.NewAgentHandler(cfg.AgentService, cfg.Logger)
		r.Get("/agents", agentH.List)
		r.Post("/agents", agentH.Create)
		r.Get("/agents/{id}", agentH.Get)
		r.Delete("/agents/{id}", agentH.Delete)
		r.Get("/agents/{id}/status", agentH.GetStatus)

		// Projects
		projectH := handlers.NewProjectHandler(cfg.ProjectService, cfg.Logger)
		r.Get("/projects", projectH.List)
		r.Post("/projects", projectH.Create)
		r.Get("/projects/{id}", projectH.Get)
		r.Put("/projects/{id}", projectH.Update)
		r.Delete("/projects/{id}", projectH.Delete)

		// Environments
		envH := handlers.NewEnvironmentHandler(cfg.EnvironmentService, cfg.Logger)
		r.Get("/environments", envH.List)
		r.Post("/environments", envH.Create)
		r.Get("/environments/{id}", envH.Get)
		r.Post("/environments/{id}/start", envH.Start)
		r.Post("/environments/{id}/stop", envH.Stop)
		r.Delete("/environments/{id}", envH.Remove)
		r.Get("/environments/{id}/logs", envH.Logs)
	})

	// SPA fallback — serve embedded frontend
	spaHandler := SPAHandler(cfg.SPAFS)
	r.Get("/", spaHandler)
	r.Get("/*", spaHandler)

	return r
}
