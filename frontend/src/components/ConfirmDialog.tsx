import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'

export interface ConfirmOptions {
  title: string
  message: string
  confirmLabel?: string
  danger?: boolean
}

type ConfirmFn = (options: ConfirmOptions) => Promise<boolean>

const ConfirmContext = createContext<ConfirmFn | null>(null)

interface Pending {
  options: ConfirmOptions
  resolve: (ok: boolean) => void
}

/** Provides `useConfirm()`: a promise-based modal for destructive actions (K-D18). */
export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<Pending | null>(null)
  const confirmButton = useRef<HTMLButtonElement>(null)

  const confirm = useCallback<ConfirmFn>(options => {
    return new Promise<boolean>(resolve => {
      setPending(prev => {
        prev?.resolve(false) // a second request supersedes the first
        return { options, resolve }
      })
    })
  }, [])

  const settle = useCallback((ok: boolean) => {
    setPending(prev => {
      prev?.resolve(ok)
      return null
    })
  }, [])

  useEffect(() => {
    if (!pending) return
    confirmButton.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') settle(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [pending, settle])

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {pending && (
        <div
          role="presentation"
          onClick={() => settle(false)}
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(17, 17, 27, 0.7)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 900,
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="confirm-title"
            aria-describedby="confirm-message"
            onClick={e => e.stopPropagation()}
            style={{
              backgroundColor: 'var(--mantle)',
              border: '1px solid var(--surface1)',
              borderRadius: 8,
              padding: 20,
              width: 'min(420px, 90vw)',
            }}
          >
            <h2 id="confirm-title" style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>
              {pending.options.title}
            </h2>
            <p id="confirm-message" style={{ fontSize: 13, color: 'var(--subtext1)', marginBottom: 16 }}>
              {pending.options.message}
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <button type="button" className="secondary" onClick={() => settle(false)}>
                Cancel
              </button>
              <button
                ref={confirmButton}
                type="button"
                className={pending.options.danger === false ? 'primary' : 'danger'}
                onClick={() => settle(true)}
              >
                {pending.options.confirmLabel ?? 'Confirm'}
              </button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components -- the hook belongs with its provider
export function useConfirm(): ConfirmFn {
  const ctx = useContext(ConfirmContext)
  if (!ctx) throw new Error('useConfirm must be used inside <ConfirmProvider>')
  return ctx
}
