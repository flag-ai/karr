import type {
  Agent, CreateAgentRequest, AgentStatus,
  Project, CreateProjectRequest, UpdateProjectRequest,
  Environment, CreateEnvironmentRequest,
  ProvisionRequest, ProvisionResponse, AgentRegistration,
} from './types'

const BASE = '/api/v1'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ error: resp.statusText }))
    throw new Error(body.error || resp.statusText)
  }
  // Handle 204 No Content
  if (resp.status === 204) return undefined as T
  return resp.json()
}

export const api = {
  // Agents
  listAgents: () => request<Agent[]>('/agents'),
  getAgent: (id: string) => request<Agent>(`/agents/${id}`),
  createAgent: (data: CreateAgentRequest) =>
    request<Agent>('/agents', { method: 'POST', body: JSON.stringify(data) }),
  deleteAgent: (id: string) =>
    request<void>(`/agents/${id}`, { method: 'DELETE' }),
  getAgentStatus: (id: string) => request<AgentStatus>(`/agents/${id}/status`),
  provisionAgent: (data: ProvisionRequest) =>
    request<ProvisionResponse>('/agents/provision', { method: 'POST', body: JSON.stringify(data) }),
  listRegistrations: () => request<AgentRegistration[]>('/agents/registrations'),
  deleteRegistration: (id: string) =>
    request<void>(`/agents/registrations/${id}`, { method: 'DELETE' }),

  // Projects
  listProjects: () => request<Project[]>('/projects'),
  getProject: (id: string) => request<Project>(`/projects/${id}`),
  createProject: (data: CreateProjectRequest) =>
    request<Project>('/projects', { method: 'POST', body: JSON.stringify(data) }),
  updateProject: (id: string, data: UpdateProjectRequest) =>
    request<Project>(`/projects/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteProject: (id: string) =>
    request<void>(`/projects/${id}`, { method: 'DELETE' }),

  // Environments
  listEnvironments: () => request<Environment[]>('/environments'),
  getEnvironment: (id: string) => request<Environment>(`/environments/${id}`),
  createEnvironment: (data: CreateEnvironmentRequest) =>
    request<Environment>('/environments', { method: 'POST', body: JSON.stringify(data) }),
  startEnvironment: (id: string) =>
    request<void>(`/environments/${id}/start`, { method: 'POST' }),
  stopEnvironment: (id: string) =>
    request<void>(`/environments/${id}/stop`, { method: 'POST' }),
  removeEnvironment: (id: string) =>
    request<void>(`/environments/${id}`, { method: 'DELETE' }),
}
