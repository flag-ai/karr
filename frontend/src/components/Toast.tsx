import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react'
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

const TOAST_TTL_MS = 6000

/** Provides `useToast()`; every mutation error surfaces here (K-D18). */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const next = useRef(1)

  const dismiss = useCallback((id: number) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  const notify = useCallback((kind: ToastKind, message: string) => {
    const id = next.current++
    setToasts(prev => [...prev.slice(-4), { id, kind, message }])
    setTimeout(() => dismiss(id), TOAST_TTL_MS)
  }, [dismiss])

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
            role={toast.kind === 'error' ? 'alert' : 'status'}
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
