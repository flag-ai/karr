import { describe, expect, it, vi } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { MAX_TOASTS, TOAST_TTL_MS, ToastProvider, useToast } from './Toast'

function Harness() {
  const toast = useToast()
  return (
    <div>
      <button onClick={() => toast.error('boom')}>err</button>
      <button onClick={() => toast.success(`ok ${Math.random()}`)}>ok</button>
    </div>
  )
}

describe('ToastProvider', () => {
  it('dedupes repeated messages, caps the stack and expires toasts', () => {
    vi.useFakeTimers()
    try {
      render(<ToastProvider><Harness /></ToastProvider>)
      act(() => { screen.getByText('err').click(); screen.getByText('err').click() })
      expect(screen.getAllByText('boom')).toHaveLength(1)
      act(() => { for (let i = 0; i < MAX_TOASTS + 3; i++) screen.getByText('ok').click() })
      expect(screen.getAllByRole('button', { name: 'Dismiss' })).toHaveLength(MAX_TOASTS)
      act(() => { vi.advanceTimersByTime(TOAST_TTL_MS + 1) })
      expect(screen.queryByRole('button', { name: 'Dismiss' })).not.toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it('announces failed queries from the window event', () => {
    render(<ToastProvider><Harness /></ToastProvider>)
    act(() => {
      window.dispatchEvent(new CustomEvent('karr:query-error', { detail: { label: 'agents', message: 'nope' } }))
    })
    expect(screen.getByText('Could not load agents: nope')).toBeInTheDocument()
  })
})
