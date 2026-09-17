import { afterEach, describe, expect, it, vi } from 'vitest'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Projects from './Projects'
import type { Project } from '../api/types'
import { jsonResponse, noContent, renderApp } from '../test/helpers'

const project: Project = {
  id: 'p1', name: 'alpha', description: 'first', created_at: '2026-09-14T00:00:00Z', updated_at: '2026-09-14T00:00:00Z',
}

afterEach(() => vi.unstubAllGlobals())

describe('Projects', () => {
  it('creates, edits inline and deletes after confirmation', async () => {
    const bodies: Array<{ method: string; url: string; body?: unknown }> = []
    vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET'
      bodies.push({ method, url, body: init?.body ? JSON.parse(init.body as string) : undefined })
      if (method === 'POST') return Promise.resolve(jsonResponse({ ...project, id: 'p2', name: 'beta' }, 201))
      if (method === 'PUT') return Promise.resolve(jsonResponse({ ...project, name: 'alpha-2' }))
      if (method === 'DELETE') return Promise.resolve(noContent())
      return Promise.resolve(jsonResponse([project]))
    }))
    renderApp(<Projects />)
    const user = userEvent.setup()
    expect(await screen.findByText('alpha')).toBeInTheDocument()

    await user.type(screen.getByLabelText('Name'), ' beta ')
    await user.type(screen.getByLabelText('Description'), 'second')
    await user.click(screen.getByRole('button', { name: 'Create Project' }))
    await vi.waitFor(() => expect(bodies.some(b => b.method === 'POST')).toBe(true))
    expect(bodies.find(b => b.method === 'POST')?.body).toEqual({ name: 'beta', description: 'second' })

    await user.click(screen.getByRole('button', { name: 'Edit' }))
    const form = screen.getByRole('form', { name: 'Edit alpha' })
    await user.clear(within(form).getByLabelText('Name'))
    await user.type(within(form).getByLabelText('Name'), 'alpha-2')
    await user.click(within(form).getByRole('button', { name: 'Save' }))
    await vi.waitFor(() => expect(bodies.some(b => b.method === 'PUT')).toBe(true))
    expect(bodies.find(b => b.method === 'PUT')).toMatchObject({ url: '/api/v1/projects/p1', body: { name: 'alpha-2', description: 'first' } })

    await user.click(screen.getByRole('button', { name: 'Delete' }))
    await user.click(within(screen.getByRole('dialog', { name: 'Delete project' })).getByRole('button', { name: 'Delete' }))
    await vi.waitFor(() => expect(bodies.some(b => b.method === 'DELETE' && b.url === '/api/v1/projects/p1')).toBe(true))
  })

  it('edits a project whose description the API omitted', async () => {
    const bare: Project = { id: 'p3', name: 'bare', created_at: project.created_at, updated_at: project.updated_at }
    const puts: unknown[] = []
    vi.stubGlobal('fetch', vi.fn((_url: string, init?: RequestInit) => {
      if (init?.method === 'PUT') {
        puts.push(JSON.parse(init.body as string))
        return Promise.resolve(jsonResponse({ ...bare, name: 'bare-2' }))
      }
      return Promise.resolve(jsonResponse([bare]))
    }))
    renderApp(<Projects />)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Edit' }))
    const form = screen.getByRole('form', { name: 'Edit bare' })
    await user.clear(within(form).getByLabelText('Name'))
    await user.type(within(form).getByLabelText('Name'), 'bare-2')
    await user.click(within(form).getByRole('button', { name: 'Save' }))
    await vi.waitFor(() => expect(puts).toEqual([{ name: 'bare-2', description: '' }]))
  })
})
