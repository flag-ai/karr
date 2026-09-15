import { afterEach, describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import Dashboard, { AgentCard } from './Dashboard'
import type { Agent, Environment } from '../api/types'
import { jsonResponse, renderApp } from '../test/helpers'

const agent: Agent = {
  id: 'a1', name: 'gpu-01', url: 'http://gpu-01:7777', status: 'online',
  created_at: '2026-09-14T00:00:00Z', updated_at: '2026-09-14T00:00:00Z',
}

afterEach(() => vi.unstubAllGlobals())

describe('AgentCard', () => {
  it('survives gpus: null from BONNIE (K-D17)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({
      agent,
      system: { system: { hostname: 'h', os: 'linux', arch: 'amd64', kernel: '6', cpu_model: 'cpu', cpu_cores: 8, memory_mb: 32768 }, disk: null },
      gpu: { vendor: 'none', gpus: null },
    })))
    renderApp(<AgentCard agent={agent} />)
    expect(await screen.findByText(/8 cores, 32 GB RAM/)).toBeInTheDocument()
    expect(screen.getByText('No GPUs reported')).toBeInTheDocument()
    expect(screen.queryByText(/Disk:/)).not.toBeInTheDocument()
  })

  it('renders a GPU card with accessible progress bars', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({
      agent,
      gpu: { vendor: 'nvidia', gpus: [{ index: 0, name: 'RTX', vendor: 'nvidia', memory_total_mib: 1000, memory_free_mib: 250, utilization_percent: 90 }] },
    })))
    renderApp(<AgentCard agent={agent} />)
    expect(await screen.findByText('GPU 0: RTX')).toBeInTheDocument()
    expect(screen.getByRole('progressbar', { name: 'Memory' })).toHaveAttribute('aria-valuenow', '75')
    expect(screen.getByRole('progressbar', { name: 'Utilization' })).toHaveAttribute('aria-valuenow', '90')
  })
})

describe('Dashboard', () => {
  it('lists agents and running environments', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (url.endsWith('/agents')) return Promise.resolve(jsonResponse([{ ...agent, status: 'offline' }]))
      if (url.endsWith('/environments')) {
        const rows: Environment[] = [
          { id: 'e1', agent_id: 'a1', name: 'env-1', image: 'img', status: 'running', gpu: false, created_at: agent.created_at, updated_at: agent.updated_at },
          { id: 'e2', agent_id: 'a1', name: 'env-2', image: 'img', status: 'stopped', gpu: false, created_at: agent.created_at, updated_at: agent.updated_at },
        ]
        return Promise.resolve(jsonResponse(rows))
      }
      return Promise.reject(new Error(`unexpected ${url}`))
    }))
    renderApp(<Dashboard />)
    expect(await screen.findByText('Agents (1)')).toBeInTheDocument()
    expect(await screen.findByText('Running Environments (1)')).toBeInTheDocument()
    expect(screen.getByText('env-1')).toBeInTheDocument()
    expect(screen.queryByText('env-2')).not.toBeInTheDocument()
  })
})
