import { StrictMode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import LogStream, { MAX_LINES } from './LogStream'
import { clearToken, setToken } from '../api/client'

function sseResponse(text: string, status = 200): Response {
  return new Response(text, { status, headers: { 'Content-Type': 'text/event-stream' } })
}

afterEach(() => {
  vi.unstubAllGlobals()
  clearToken()
})

describe('LogStream', () => {
  it('sends the bearer token, unescapes lines and stops on event: end', async () => {
    setToken('tok')
    const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(sseResponse(
      'data: first\n\n: keepalive\n\ndata: two\\nlines\n\nevent: end\ndata: \n\n',
    )))
    vi.stubGlobal('fetch', fetchMock)
    render(<LogStream environmentId="e1" />)
    expect(await screen.findByText('Stream ended.')).toBeInTheDocument()
    const log = screen.getByRole('log')
    expect(log).toHaveTextContent('first')
    expect(log.textContent).toContain('two\nlines')
    const init = fetchMock.mock.calls[0]?.[1]
    expect((init?.headers as Record<string, string>).Authorization).toBe('Bearer tok')
    expect(fetchMock).toHaveBeenCalledTimes(1) // an intentional end is not retried
  })

  it('survives StrictMode double mounting with one live stream and no duplicated lines', async () => {
    const fetchMock = vi.fn(() => Promise.resolve(sseResponse('data: only\n\nevent: end\ndata: \n\n')))
    vi.stubGlobal('fetch', fetchMock)
    render(<StrictMode><LogStream environmentId="e1" /></StrictMode>)
    expect(await screen.findByText('Stream ended.')).toBeInTheDocument()
    expect(screen.getByRole('log').children).toHaveLength(1)
    expect(fetchMock).toHaveBeenCalledTimes(2) // mount, unmount (aborted), mount
  })

  it('shows event: error and the server message for a rejected stream', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(sseResponse('event: error\ndata: container gone\n\n'))))
    render(<LogStream environmentId="e1" />)
    expect(await screen.findByText('Stream error: container gone')).toBeInTheDocument()

    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(
      new Response(JSON.stringify({ error: 'environment has no container' }), { status: 409, headers: { 'Content-Type': 'application/json' } }),
    )))
    render(<LogStream environmentId="e2" />)
    expect(await screen.findByText('Stream error: environment has no container')).toBeInTheDocument()
  })

  it('announces a 401 so the AuthGate re-prompts', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response('{"error":"unauthorized"}', { status: 401 }))))
    const seen = vi.fn()
    window.addEventListener('karr:unauthorized', seen)
    render(<LogStream environmentId="e1" />)
    expect(await screen.findByText('Stream error: unauthorized')).toBeInTheDocument()
    expect(seen).toHaveBeenCalledTimes(1)
    window.removeEventListener('karr:unauthorized', seen)
  })

  it('keeps at most MAX_LINES lines', async () => {
    const frames = Array.from({ length: MAX_LINES + 10 }, (_, i) => `data: line ${i}\n\n`).join('') + 'event: end\ndata: \n\n'
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(sseResponse(frames))))
    render(<LogStream environmentId="e1" />)
    await screen.findByText('Stream ended.')
    const log = screen.getByRole('log')
    await waitFor(() => expect(log.children.length).toBe(MAX_LINES))
    expect(log.firstChild).toHaveTextContent('line 10')
    expect(log.lastChild).toHaveTextContent(`line ${MAX_LINES + 9}`)
  })

  it('reconnects with backoff and marks the restart', async () => {
    vi.useFakeTimers()
    try {
      const fetchMock = vi.fn()
        .mockRejectedValueOnce(new TypeError('network down'))
        .mockRejectedValueOnce(new TypeError('still down'))
        .mockImplementationOnce(() => Promise.resolve(sseResponse('data: back\n\nevent: end\ndata: \n\n')))
      vi.stubGlobal('fetch', fetchMock)
      render(<LogStream environmentId="e1" />)
      await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
      await vi.advanceTimersByTimeAsync(1000) // first retry after 1 s
      await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
      await vi.advanceTimersByTimeAsync(1500) // second retry only after 2 s
      expect(fetchMock).toHaveBeenCalledTimes(2)
      await vi.advanceTimersByTimeAsync(600)
      await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3))
      await vi.waitFor(() => expect(screen.getByText('Stream ended.')).toBeInTheDocument())
      expect(screen.getByRole('log').firstChild).toHaveTextContent('log restarted')
      expect(screen.getByRole('log').lastChild).toHaveTextContent('back')
    } finally {
      vi.useRealTimers()
    }
  })
})
