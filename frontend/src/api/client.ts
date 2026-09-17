import type {
  Agent, CreateAgentRequest, AgentStatus,
  Project, CreateProjectRequest, UpdateProjectRequest,
  Environment, CreateEnvironmentRequest,
  ProvisionRequest, ProvisionResponse, AgentRegistration,
} from './types'

export const BASE = '/api/v1'
const TOKEN_KEY = 'karr_admin_token'

// The admin token lives in sessionStorage only: it is gone when the tab closes
// and never written to localStorage or a cookie.
let token: string | null = readStoredToken()

function readStoredToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

/** Remember the token; with `persist: false` it lives in memory only until verified. */
export function setToken(value: string, persist = true): void {
  token = value
  if (!persist) return
  try {
    sessionStorage.setItem(TOKEN_KEY, value)
  } catch {
    // storage disabled: the token still lives for this page load
  }
}

export function clearToken(): void {
  token = null
  try {
    sessionStorage.removeItem(TOKEN_KEY)
  } catch {
    // nothing stored
  }
}

export function hasToken(): boolean {
  return token !== null && token !== ''
}

export function authHeaders(): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

function isJson(resp: Response): boolean {
  const type = resp.headers.get('content-type') ?? ''
  return type.split(';', 1)[0]?.trim().toLowerCase() === 'application/json'
}

/** Read the `{"error": ...}` envelope; fall back to the status text (K-D18). */
async function errorMessage(resp: Response): Promise<string> {
  if (isJson(resp)) {
    try {
      const body: unknown = await resp.json()
      if (body && typeof body === 'object' && 'error' in body) {
        const err = (body as { error: unknown }).error
        if (typeof err === 'string' && err) return err
      }
    } catch {
      // fall through
    }
  }
  return resp.statusText || `request failed (${resp.status})`
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...(options.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
    ...authHeaders(),
    ...(options.headers as Record<string, string> | undefined),
  }

  let resp: Response
  try {
    resp = await fetch(BASE + path, { ...options, headers })
  } catch {
    throw new ApiError(0, 'cannot reach the KARR server')
  }
  if (!resp.ok) {
    if (resp.status === 401 && path !== '/auth/check') {
      // the token was rotated or the session storage was cleared: re-prompt
      window.dispatchEvent(new Event('karr:unauthorized'))
    }
    throw new ApiError(resp.status, await errorMessage(resp))
  }
  if (resp.status === 204) return undefined as T
  if (!isJson(resp)) {
    // a proxy login page or an HTML error must not be parsed as data (K-D18)
    throw new ApiError(resp.status, 'unexpected non-JSON response from the server')
  }
  return resp.json() as Promise<T>
}

const enc = encodeURIComponent

export const api = {
  /** 204 with a valid token, 401 otherwise; used by the AuthGate. */
  authCheck: () => request<void>('/auth/check'),

  // Agents
  listAgents: () => request<Agent[]>('/agents'),
  getAgent: (id: string) => request<Agent>(`/agents/${enc(id)}`),
  createAgent: (data: CreateAgentRequest) =>
    request<Agent>('/agents', { method: 'POST', body: JSON.stringify(data) }),
  deleteAgent: (id: string) =>
    request<void>(`/agents/${enc(id)}`, { method: 'DELETE' }),
  getAgentStatus: (id: string) => request<AgentStatus>(`/agents/${enc(id)}/status`),
  provisionAgent: (data: ProvisionRequest) =>
    request<ProvisionResponse>('/agents/provision', { method: 'POST', body: JSON.stringify(data) }),
  listRegistrations: () => request<AgentRegistration[]>('/agents/registrations'),
  deleteRegistration: (id: string) =>
    request<void>(`/agents/registrations/${enc(id)}`, { method: 'DELETE' }),

  // Projects
  listProjects: () => request<Project[]>('/projects'),
  getProject: (id: string) => request<Project>(`/projects/${enc(id)}`),
  createProject: (data: CreateProjectRequest) =>
    request<Project>('/projects', { method: 'POST', body: JSON.stringify(data) }),
  updateProject: (id: string, data: UpdateProjectRequest) =>
    request<Project>(`/projects/${enc(id)}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteProject: (id: string) =>
    request<void>(`/projects/${enc(id)}`, { method: 'DELETE' }),

  // Environments
  listEnvironments: () => request<Environment[]>('/environments'),
  getEnvironment: (id: string) => request<Environment>(`/environments/${enc(id)}`),
  createEnvironment: (data: CreateEnvironmentRequest) =>
    request<Environment>('/environments', { method: 'POST', body: JSON.stringify(data) }),
  startEnvironment: (id: string) =>
    request<void>(`/environments/${enc(id)}/start`, { method: 'POST' }),
  stopEnvironment: (id: string) =>
    request<void>(`/environments/${enc(id)}/stop`, { method: 'POST' }),
  removeEnvironment: (id: string) =>
    request<void>(`/environments/${enc(id)}`, { method: 'DELETE' }),
  environmentLogsUrl: (id: string) => `${BASE}/environments/${id}/logs`,
}

export function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.message
  if (err instanceof Error) return err.message
  return String(err)
}
