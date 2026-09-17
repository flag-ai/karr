import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import AuthGate from './AuthGate'
import { clearToken, hasToken, setToken } from '../api/client'
import { jsonResponse, noContent } from '../test/helpers'

afterEach(() => {
  vi.unstubAllGlobals()
  clearToken()
})

describe('AuthGate', () => {
  it('shows the sign-in form without a token and does not call the API', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    render(<AuthGate><p>app</p></AuthGate>)
    expect(screen.getByRole('form', { name: 'Sign in' })).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('renders children once /auth/check answers 204', async () => {
    setToken('good')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(noContent()))
    render(<AuthGate><p>app</p></AuthGate>)
    expect(await screen.findByText('app')).toBeInTheDocument()
  })

  it('clears a rejected token and reports it', async () => {
    setToken('stale')
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ error: 'unauthorized' }, 401))
    vi.stubGlobal('fetch', fetchMock)
    render(<AuthGate><p>app</p></AuthGate>)
    expect(await screen.findByRole('form', { name: 'Sign in' })).toBeInTheDocument()
    expect(hasToken()).toBe(false)

    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Admin token'), 'wrong')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid admin token.')
    expect(hasToken()).toBe(false)

    fetchMock.mockResolvedValue(noContent())
    await user.clear(screen.getByLabelText('Admin token'))
    await user.type(screen.getByLabelText('Admin token'), 'right')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByText('app')).toBeInTheDocument()
    await waitFor(() => expect(sessionStorage.getItem('karr_admin_token')).toBe('right'))
  })

  it('falls back to the form when a later request answers 401', async () => {
    setToken('good')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(noContent()))
    render(<AuthGate><p>app</p></AuthGate>)
    await screen.findByText('app')
    window.dispatchEvent(new Event('karr:unauthorized'))
    expect(await screen.findByRole('form', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('shows a server error when the API is unreachable', async () => {
    setToken('good')
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    render(<AuthGate><p>app</p></AuthGate>)
    expect(await screen.findByText('Cannot reach the KARR server.')).toBeInTheDocument()
  })
})
