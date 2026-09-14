import { afterEach, describe, expect, it, vi } from 'vitest'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Agents from './Agents'
import type { Agent, AgentRegistration, ProvisionResponse } from '../api/types'
import { jsonResponse, noContent, renderApp } from '../test/helpers'

const agent: Agent = {
  id: 'a1', name: 'gpu-01', url: 'http://gpu-01:7777', status: 'online',
  created_at: '2026-09-14T00:00:00Z', updated_at: '2026-09-14T00:00:00Z',
}
const pending: AgentRegistration = {
  id: 'r1', label: 'lab-1', status: 'pending', created_at: '2026-09-14T00:00:00Z', expires_at: '2099-01-01T00:00:00Z',
}
const provisioned: ProvisionResponse = {
  id: 'r2', token: 'one-time', install_command: 'curl -fsSL https://karr/install.sh | sudo bash -s --', expires_at: '2099-01-01T00:00:00Z',
}

afterEach(() => vi.unstubAllGlobals())

describe('Agents', () => {
  it('provisions an install command and confirms before cancelling or removing', async () => {
    const calls: string[] = []
    vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
      calls.push(`${init?.method ?? 'GET'} ${url}`)
      if (init?.method === 'POST' && url.endsWith('/agents/provision')) {
        expect(JSON.parse(init.body as string)).toEqual({ label: 'lab-2' })
        return Promise.resolve(jsonResponse(provisioned, 201))
      }
      if (init?.method === 'DELETE') return Promise.resolve(noContent())
      if (url.endsWith('/agents')) return Promise.resolve(jsonResponse([agent]))
      if (url.endsWith('/agents/registrations')) return Promise.resolve(jsonResponse([pending]))
      return Promise.reject(new Error(`unexpected ${url}`))
    }))
    renderApp(<Agents />)
    const user = userEvent.setup()

    expect(await screen.findByText('gpu-01')).toBeInTheDocument()
    expect(await screen.findByText('lab-1')).toBeInTheDocument()

    await user.type(screen.getByLabelText('Label'), ' lab-2 ')
    await user.click(screen.getByRole('button', { name: 'Generate Install Command' }))
    expect(await screen.findByText(provisioned.install_command)).toBeInTheDocument()
    expect(screen.getByText(/expires in/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    const dialog = screen.getByRole('dialog', { name: 'Cancel registration' })
    await user.click(within(dialog).getByRole('button', { name: 'Cancel registration' }))
    await vi.waitFor(() => expect(calls).toContain('DELETE /api/v1/agents/registrations/r1'))

    await user.click(screen.getByRole('button', { name: 'Remove' }))
    await user.click(within(screen.getByRole('dialog', { name: 'Remove agent' })).getByRole('button', { name: 'Cancel' }))
    expect(calls).not.toContain('DELETE /api/v1/agents/a1')
    await user.click(screen.getByRole('button', { name: 'Remove' }))
    await user.click(within(screen.getByRole('dialog', { name: 'Remove agent' })).getByRole('button', { name: 'Remove' }))
    await vi.waitFor(() => expect(calls).toContain('DELETE /api/v1/agents/a1'))
  })

  it('reports a provisioning failure as a toast', async () => {
    vi.stubGlobal('fetch', vi.fn((_url: string, init?: RequestInit) => {
      if (init?.method === 'POST') return Promise.resolve(jsonResponse({ error: 'KARR_PUBLIC_URL is not set' }, 503))
      return Promise.resolve(jsonResponse([]))
    }))
    renderApp(<Agents />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Label'), 'x')
    await user.click(screen.getByRole('button', { name: 'Generate Install Command' }))
    expect(await screen.findByText('Provisioning failed: KARR_PUBLIC_URL is not set')).toBeInTheDocument()
  })
})
