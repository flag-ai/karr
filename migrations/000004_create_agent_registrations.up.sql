CREATE TABLE karr_agent_registrations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    token_hash  TEXT NOT NULL UNIQUE,
    label       TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'pending',
    agent_id    UUID REFERENCES karr_agents(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    claimed_at  TIMESTAMPTZ,
    expires_at  TIMESTAMPTZ NOT NULL DEFAULT now() + INTERVAL '1 hour'
);
