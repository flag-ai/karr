export interface Agent {
  id: string
  name: string
  url: string
  status: 'online' | 'offline' | 'error'
  last_seen_at?: string
  created_at: string
  updated_at: string
}

export interface CreateAgentRequest {
  name: string
  url: string
  token: string
}

export interface ProvisionRequest {
  label: string
}

export interface ProvisionResponse {
  id: string
  token: string
  install_command: string
  expires_at: string
}

export interface AgentRegistration {
  id: string
  label: string
  status: 'pending' | 'claimed' | 'expired'
  agent_id?: string
  created_at: string
  claimed_at?: string
  expires_at: string
}

export interface GPUInfo {
  index: number
  name: string
  vendor: string
  memory_total_mib: number
  memory_free_mib: number
  utilization_percent: number
}

export interface GPUSnapshot {
  vendor: string
  gpus: GPUInfo[]
  timestamp: string
}

export interface SystemInfo {
  hostname: string
  os: string
  arch: string
  kernel: string
  cpu_model: string
  cpu_cores: number
  memory_mb: number
}

export interface DiskUsage {
  total_gb: number
  used_gb: number
  available_gb: number
  used_percent: string
}

export interface SystemInfoResponse {
  system: SystemInfo
  disk: DiskUsage
}

export interface AgentStatus {
  agent: Agent
  system?: SystemInfoResponse
  gpu?: GPUSnapshot
}

export interface Project {
  id: string
  name: string
  description: string
  created_at: string
  updated_at: string
}

export interface CreateProjectRequest {
  name: string
  description: string
}

export interface UpdateProjectRequest {
  name?: string
  description?: string
}

export interface Environment {
  id: string
  project_id?: string
  agent_id: string
  name: string
  image: string
  container_id: string
  status: 'creating' | 'running' | 'stopped' | 'error' | 'removed'
  gpu: boolean
  env: string[]
  mounts: string[]
  command: string[]
  created_at: string
  updated_at: string
}

export interface CreateEnvironmentRequest {
  project_id?: string
  agent_id: string
  name: string
  image: string
  gpu: boolean
  env?: string[]
  mounts?: string[]
  command?: string[]
}
