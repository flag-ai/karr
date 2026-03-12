CREATE TABLE karr_environments (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id   UUID REFERENCES karr_projects(id) ON DELETE SET NULL,
    agent_id     UUID NOT NULL REFERENCES karr_agents(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    image        TEXT NOT NULL,
    container_id TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'creating',
    gpu          BOOLEAN NOT NULL DEFAULT false,
    env          JSONB NOT NULL DEFAULT '[]',
    mounts       JSONB NOT NULL DEFAULT '[]',
    command      JSONB NOT NULL DEFAULT '[]',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_karr_environments_agent_id ON karr_environments(agent_id);
CREATE INDEX idx_karr_environments_project_id ON karr_environments(project_id);
