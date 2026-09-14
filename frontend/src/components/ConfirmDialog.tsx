import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'

export interface ConfirmOptions {
  title: string
  message: string
  confirmLabel?: string
  /** Style the confirm button as destructive (the default: every caller today is). */
  danger?: boolean
}

type ConfirmFn = (options: ConfirmOptions) => Promise<boolean>

const ConfirmContext = createContext<ConfirmFn | null>(null)

const FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

/** Provides `useConfirm()`: a promise-based modal for destructive actions (K-D18). */
export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [options, setOptions] = useState<ConfirmOptions | null>(null)
  const resolver = useRef<((ok: boolean) => void) | null>(null)
  const restoreTo = useRef<HTMLElement | null>(null)
  const dialog = useRef<HTMLDivElement>(null)
  const confirmButton = useRef<HTMLButtonElement>(null)

  const settle = useCallback((ok: boolean) => {
    const resolve = resolver.current
    resolver.current = null
    setOptions(null)
    resolve?.(ok)
    restoreTo.current?.focus()
    restoreTo.current = null
  }, [])

  const confirm = useCallback<ConfirmFn>(next => {
    resolver.current?.(false) // a second request supersedes the first
    restoreTo.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    return new Promise<boolean>(resolve => {
      resolver.current = resolve
      setOptions(next)
    })
  }, [])

  // an unmounted provider must not leave callers awaiting forever
  useEffect(() => () => resolver.current?.(false), [])

  useEffect(() => {
    if (!options) return
    confirmButton.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        settle(false)
        return
      }
      if (e.key !== 'Tab' || !dialog.current) return
      // keep focus inside the dialog
      const focusable = Array.from(dialog.current.querySelectorAll<HTMLElement>(FOCUSABLE))
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (!first || !last) return
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      } else if (!dialog.current.contains(document.activeElement)) {
        e.preventDefault()
        first.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [options, settle])

  const danger = options?.danger ?? true

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {options && (
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
            ref={dialog}
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
              {options.title}
            </h2>
            <p id="confirm-message" style={{ fontSize: 13, color: 'var(--subtext1)', marginBottom: 16 }}>
              {options.message}
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <button type="button" className="secondary" onClick={() => settle(false)}>
                Cancel
              </button>
              <button ref={confirmButton} type="button" className={danger ? 'danger' : 'primary'} onClick={() => settle(true)}>
                {options.confirmLabel ?? 'Confirm'}
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
