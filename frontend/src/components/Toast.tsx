import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'

export type ToastKind = 'error' | 'success' | 'info'

export interface Toast {
  id: number
  kind: ToastKind
  message: string
}

interface ToastApi {
  notify: (kind: ToastKind, message: string) => void
  error: (message: string) => void
  success: (message: string) => void
}

const ToastContext = createContext<ToastApi | null>(null)

const KIND_COLOR: Record<ToastKind, string> = {
  error: 'var(--red)',
  success: 'var(--green)',
  info: 'var(--blue)',
}

export const TOAST_TTL_MS = 6000
export const MAX_TOASTS = 5

/** Fired by the query cache for a failed background query (see main.tsx). */
export interface QueryErrorDetail {
  label: string
  message: string
}

/** Provides `useToast()`; every mutation and query error surfaces here (K-D18). */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const next = useRef(1)
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>())

  const dismiss = useCallback((id: number) => {
    const timer = timers.current.get(id)
    if (timer !== undefined) clearTimeout(timer)
    timers.current.delete(id)
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  const notify = useCallback((kind: ToastKind, message: string) => {
    setToasts(prev => {
      if (prev.some(t => t.kind === kind && t.message === message)) return prev // a polling query repeats itself
      const id = next.current++
      timers.current.set(id, setTimeout(() => dismiss(id), TOAST_TTL_MS))
      const kept = prev.length >= MAX_TOASTS ? prev.slice(prev.length - MAX_TOASTS + 1) : prev
      for (const evicted of prev.slice(0, prev.length - kept.length)) {
        const timer = timers.current.get(evicted.id)
        if (timer !== undefined) clearTimeout(timer)
        timers.current.delete(evicted.id)
      }
      return [...kept, { id, kind, message }]
    })
  }, [dismiss])

  useEffect(() => {
    const pending = timers.current
    const onQueryError = (e: Event) => {
      const { label, message } = (e as CustomEvent<QueryErrorDetail>).detail
      notify('error', `Could not load ${label}: ${message}`)
    }
    window.addEventListener('karr:query-error', onQueryError)
    return () => {
      window.removeEventListener('karr:query-error', onQueryError)
      for (const timer of pending.values()) clearTimeout(timer)
      pending.clear()
    }
  }, [notify])

  const value = useMemo<ToastApi>(() => ({
    notify,
    error: (message: string) => notify('error', message),
    success: (message: string) => notify('success', message),
  }), [notify])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        aria-label="Notifications"
        style={{
          position: 'fixed',
          right: 16,
          bottom: 16,
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
          zIndex: 1000,
          maxWidth: 420,
        }}
      >
        {toasts.map(toast => (
          <div
            key={toast.id}
            data-kind={toast.kind}
            style={{
              backgroundColor: 'var(--mantle)',
              borderLeft: `4px solid ${KIND_COLOR[toast.kind]}`,
              borderRadius: 6,
              padding: '10px 12px',
              fontSize: 13,
              color: 'var(--text)',
              boxShadow: '0 4px 16px rgba(0,0,0,0.4)',
              display: 'flex',
              justifyContent: 'space-between',
              gap: 12,
            }}
          >
            <span style={{ wordBreak: 'break-word' }}>{toast.message}</span>
            <button
              type="button"
              aria-label="Dismiss"
              onClick={() => dismiss(toast.id)}
              style={{ background: 'none', padding: 0, color: 'var(--overlay1)', fontSize: 14 }}
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components -- the hook belongs with its provider
export function useToast(): ToastApi {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used inside <ToastProvider>')
  return ctx
}
