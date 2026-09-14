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
    const fetchMock = vi.fn().mockResolvedValue(sseResponse(
      'data: first\n\n: keepalive\n\ndata: two\\nlines\n\nevent: end\ndata: \n\n',
    ))
    vi.stubGlobal('fetch', fetchMock)
    render(<LogStream environmentId="e1" active={true} />)
    expect(await screen.findByText('Stream ended.')).toBeInTheDocument()
    const log = screen.getByRole('log')
    expect(log).toHaveTextContent('first')
    expect(log.textContent).toContain('two\nlines')
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer tok')
    expect(fetchMock).toHaveBeenCalledTimes(1) // an intentional end is not retried
  })

  it('shows event: error and the server message for a rejected stream', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse('event: error\ndata: container gone\n\n')))
    render(<LogStream environmentId="e1" active={true} />)
    expect(await screen.findByText('Stream error: container gone')).toBeInTheDocument()

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error: 'environment has no container' }), { status: 409, headers: { 'Content-Type': 'application/json' } }),
    ))
    render(<LogStream environmentId="e2" active={true} />)
    expect(await screen.findByText('Stream error: environment has no container')).toBeInTheDocument()
  })

  it('keeps at most MAX_LINES lines', async () => {
    const frames = Array.from({ length: MAX_LINES + 10 }, (_, i) => `data: line ${i}\n\n`).join('') + 'event: end\ndata: \n\n'
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse(frames)))
    render(<LogStream environmentId="e1" active={true} />)
    await screen.findByText('Stream ended.')
    const log = screen.getByRole('log')
    await waitFor(() => expect(log.children.length).toBe(MAX_LINES))
    expect(log.firstChild).toHaveTextContent('line 10')
    expect(log.lastChild).toHaveTextContent(`line ${MAX_LINES + 9}`)
  })

  it('reconnects after a dropped connection', async () => {
    vi.useFakeTimers()
    try {
      const fetchMock = vi.fn()
        .mockRejectedValueOnce(new TypeError('network down'))
        .mockResolvedValueOnce(sseResponse('data: back\n\nevent: end\ndata: \n\n'))
      vi.stubGlobal('fetch', fetchMock)
      render(<LogStream environmentId="e1" active={true} />)
      await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
      await vi.advanceTimersByTimeAsync(1000)
      await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
      await vi.waitFor(() => expect(screen.getByText('Stream ended.')).toBeInTheDocument())
    } finally {
      vi.useRealTimers()
    }
  })
})
