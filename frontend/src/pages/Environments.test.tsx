import { afterEach, describe, expect, it, vi } from 'vitest'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Environments from './Environments'
import type { Environment } from '../api/types'
import { jsonResponse, noContent, renderApp } from '../test/helpers'

const env: Environment = {
  id: 'e1', agent_id: 'a1', name: 'env-1', image: 'img', status: 'running', gpu: true, container_id: 'c1',
  created_at: '2026-09-14T00:00:00Z', updated_at: '2026-09-14T00:00:00Z',
}

afterEach(() => vi.unstubAllGlobals())

describe('Environments', () => {
  it('asks before stopping and shows the API error as a toast (K-D18)', async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === 'POST' && url.endsWith('/stop')) {
        return Promise.resolve(jsonResponse({ error: 'stop container failed: agent unreachable' }, 502))
      }
      if (url.endsWith('/environments')) return Promise.resolve(jsonResponse([env]))
      if (url.endsWith('/agents') || url.endsWith('/projects')) return Promise.resolve(jsonResponse([]))
      return Promise.resolve(noContent())
    })
    vi.stubGlobal('fetch', fetchMock)
    renderApp(<Environments />)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Stop' }))
    expect(screen.getByRole('dialog', { name: 'Stop environment' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(fetchMock.mock.calls.some(([url]) => (url as string).endsWith('/stop'))).toBe(false)

    await user.click(screen.getByRole('button', { name: 'Stop' }))
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Stop' }))
    expect(await screen.findByText('Stop failed: stop container failed: agent unreachable')).toBeInTheDocument()
  })

  it('toasts a failed list query instead of showing an empty list', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (url.endsWith('/environments')) return Promise.resolve(jsonResponse({ error: 'database unavailable' }, 500))
      return Promise.resolve(jsonResponse([]))
    }))
    renderApp(<Environments />)
    expect(await screen.findByText('Could not load environments: database unavailable')).toBeInTheDocument()
  })
})
