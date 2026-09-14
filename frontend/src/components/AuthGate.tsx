import { useCallback, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { ApiError, api, clearToken, hasToken, setToken } from '../api/client'

/**
 * Asks for the admin token until `GET /api/v1/auth/check` answers 204 (K-D1).
 * The token is kept in sessionStorage by the API client.
 */
export default function AuthGate({ children }: { children: ReactNode }) {
  const [authed, setAuthed] = useState<boolean | null>(null)
  const [serverError, setServerError] = useState('')
  const [input, setInput] = useState('')
  const [loginError, setLoginError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const check = useCallback(async () => {
    if (!hasToken()) {
      setAuthed(false)
      return
    }
    try {
      await api.authCheck()
      setAuthed(true)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        clearToken()
        setAuthed(false)
      } else if (err instanceof ApiError && err.status === 0) {
        setServerError('Cannot reach the KARR server.')
      } else {
        setServerError(err instanceof Error ? err.message : String(err))
      }
    }
  }, [])

  useEffect(() => {
    void check()
  }, [check])

  // A 401 from any later request (token rotated) sends the user back here.
  useEffect(() => {
    const onUnauthorized = () => {
      clearToken()
      setAuthed(false)
    }
    window.addEventListener('karr:unauthorized', onUnauthorized)
    return () => window.removeEventListener('karr:unauthorized', onUnauthorized)
  }, [])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    const value = input.trim()
    if (!value) return
    setSubmitting(true)
    setLoginError('')
    setToken(value)
    try {
      await api.authCheck()
      setInput('')
      setAuthed(true)
    } catch (err) {
      clearToken()
      if (err instanceof ApiError && err.status === 401) {
        setLoginError('Invalid admin token.')
      } else {
        setLoginError('Connection failed. Check that KARR is running.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  if (serverError) {
    return (
      <Centered>
        <div style={{ ...card, borderColor: 'var(--red)' }}>
          <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>Server error</h2>
          <p style={{ fontSize: 13, color: 'var(--subtext0)' }}>{serverError}</p>
          <button type="button" className="secondary" style={{ marginTop: 16 }} onClick={() => { setServerError(''); void check() }}>
            Retry
          </button>
        </div>
      </Centered>
    )
  }

  if (authed === null) {
    return (
      <Centered>
        <p style={{ color: 'var(--subtext0)' }}>Connecting…</p>
      </Centered>
    )
  }

  if (!authed) {
    return (
      <Centered>
        <form onSubmit={submit} style={card} aria-label="Sign in">
          <h1 style={{ fontSize: 20, fontWeight: 700, color: 'var(--blue)', letterSpacing: 2, marginBottom: 4 }}>KARR</h1>
          <p style={{ fontSize: 13, color: 'var(--subtext0)', marginBottom: 16 }}>Enter the admin token to continue.</p>
          {loginError && (
            <div role="alert" style={{ color: 'var(--red)', fontSize: 12, marginBottom: 12 }}>{loginError}</div>
          )}
          <label style={{ display: 'block', fontSize: 12, color: 'var(--subtext1)', marginBottom: 12 }}>
            Admin token
            <input
              type="password"
              value={input}
              onChange={e => setInput(e.target.value)}
              autoComplete="current-password"
              autoFocus
              style={{ display: 'block', width: '100%', marginTop: 4 }}
            />
          </label>
          <button type="submit" className="primary" disabled={submitting || !input.trim()} style={{ width: '100%' }}>
            {submitting ? 'Verifying…' : 'Sign in'}
          </button>
        </form>
      </Centered>
    )
  }

  return <>{children}</>
}

const card: React.CSSProperties = {
  backgroundColor: 'var(--mantle)',
  border: '1px solid var(--surface0)',
  borderRadius: 8,
  padding: 24,
  width: 'min(360px, 90vw)',
}

function Centered({ children }: { children: ReactNode }) {
  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: 'var(--base)' }}>
      {children}
    </div>
  )
}
