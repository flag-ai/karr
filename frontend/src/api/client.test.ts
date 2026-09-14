import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, api, authHeaders, clearToken, hasToken, setToken } from './client'
import { jsonResponse, noContent } from '../test/helpers'

afterEach(() => {
  vi.unstubAllGlobals()
  clearToken()
})

describe('token store', () => {
  it('keeps the token in sessionStorage only', () => {
    expect(hasToken()).toBe(false)
    setToken('secret-token')
    expect(sessionStorage.getItem('karr_admin_token')).toBe('secret-token')
    expect(authHeaders()).toEqual({ Authorization: 'Bearer secret-token' })
    clearToken()
    expect(authHeaders()).toEqual({})
  })
})

describe('request', () => {
  it('sends the bearer header and parses JSON', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([{ id: 'a1' }]))
    vi.stubGlobal('fetch', fetchMock)
    setToken('tok')
    await expect(api.listAgents()).resolves.toEqual([{ id: 'a1' }])
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/agents')
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer tok')
  })

  it('surfaces the error envelope', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ error: 'agent not found' }, 400)))
    await expect(api.getAgent('x')).rejects.toMatchObject({ status: 400, message: 'agent not found' })
  })

  it('rejects a non-JSON success body (K-D18)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response('<html>login</html>', { status: 200, headers: { 'Content-Type': 'text/html' } }),
    ))
    await expect(api.listProjects()).rejects.toBeInstanceOf(ApiError)
    await expect(api.listProjects()).rejects.toThrow(/non-JSON/)
  })

  it('treats 204 as success without a body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(noContent()))
    await expect(api.deleteProject('p')).resolves.toBeUndefined()
  })

  it('announces a 401 so the AuthGate re-prompts', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ error: 'unauthorized' }, 401)))
    const seen = vi.fn()
    window.addEventListener('karr:unauthorized', seen)
    await expect(api.listAgents()).rejects.toMatchObject({ status: 401 })
    expect(seen).toHaveBeenCalledTimes(1)
    window.removeEventListener('karr:unauthorized', seen)
  })

  it('maps a network failure to status 0', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(api.authCheck()).rejects.toMatchObject({ status: 0 })
  })
})
