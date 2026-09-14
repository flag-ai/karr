import { useEffect, useRef, useState } from 'react'
import { api, authHeaders } from '../api/client'
import { readEvents, unescapeLine } from '../api/sse'

interface Props {
  environmentId: string
}

export const MAX_LINES = 5000
const RECONNECT_BASE_MS = 1000
const RECONNECT_MAX_MS = 30000
const RESTART_MARKER = '— connection lost; log restarted from the container tail —'

type Phase = 'connecting' | 'streaming' | 'ended' | 'error' | 'reconnecting'

/**
 * Relays the container log SSE stream (K-D2): reads it over fetch so the
 * bearer token can be sent, keeps at most MAX_LINES, unescapes the frames,
 * reconnects with backoff after a dropped connection, and stops cleanly on
 * `event: end` / `event: error`.
 */
export default function LogStream({ environmentId }: Props) {
  const [lines, setLines] = useState<string[]>([])
  const [phase, setPhase] = useState<Phase>('connecting')
  const [detail, setDetail] = useState('')
  const containerRef = useRef<HTMLDivElement>(null)
  const stickToBottom = useRef(true)

  useEffect(() => {
    const controller = new AbortController()
    const { signal } = controller
    let attempt = 0
    let timer: ReturnType<typeof setTimeout> | undefined
    setLines([])
    setDetail('')

    const append = (line: string) => {
      setLines(prev => {
        const next = prev.length >= MAX_LINES ? prev.slice(prev.length - MAX_LINES + 1) : prev.slice()
        next.push(line)
        return next
      })
    }

    const fail = (message: string) => {
      if (signal.aborted) return
      setDetail(message)
      setPhase('error')
    }

    const connect = async (): Promise<void> => {
      if (signal.aborted) return
      setPhase(attempt === 0 ? 'connecting' : 'reconnecting')
      let resp: Response
      try {
        resp = await fetch(api.environmentLogsUrl(environmentId), {
          headers: { Accept: 'text/event-stream', ...authHeaders() },
          signal,
        })
      } catch {
        if (!signal.aborted) scheduleReconnect()
        return
      }
      if (signal.aborted) return
      if (resp.status === 401) {
        window.dispatchEvent(new Event('karr:unauthorized'))
        fail('unauthorized')
        return
      }
      if (!resp.ok) {
        // 404/409 will not change on retry; show the server's message
        let message = `${resp.status} ${resp.statusText}`
        try {
          const body = (await resp.json()) as { error?: string }
          if (body.error) message = body.error
        } catch {
          // keep the status line
        }
        fail(message)
        return
      }
      if (!resp.body) {
        fail('the server sent no stream')
        return
      }
      if (attempt > 0) append(RESTART_MARKER) // the relay restarts from the tail: no cursor
      setPhase('streaming')
      let received = false
      try {
        for await (const event of readEvents(resp.body, signal)) {
          if (!received) {
            received = true
            attempt = 0 // only a stream that delivered something resets the backoff
          }
          if (event.event === 'end') {
            if (!signal.aborted) setPhase('ended')
            return
          }
          if (event.event === 'error') {
            fail(event.data || 'stream failed')
            return
          }
          append(unescapeLine(event.data))
        }
      } catch {
        // dropped mid-stream: fall through to reconnect
      }
      if (!signal.aborted) scheduleReconnect()
    }

    const scheduleReconnect = () => {
      const delay = Math.min(RECONNECT_MAX_MS, RECONNECT_BASE_MS * 2 ** attempt)
      attempt += 1
      setPhase('reconnecting')
      timer = setTimeout(() => void connect(), delay)
    }

    void connect()
    return () => {
      controller.abort()
      if (timer !== undefined) clearTimeout(timer)
    }
  }, [environmentId])

  useEffect(() => {
    const el = containerRef.current
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight
  }, [lines])

  const onScroll = () => {
    const el = containerRef.current
    if (el) stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24
  }

  return (
    <div>
      <div
        ref={containerRef}
        onScroll={onScroll}
        role="log"
        aria-live="off"
        aria-label="Container logs"
        style={{
          backgroundColor: 'var(--crust)',
          borderRadius: 8,
          padding: 12,
          fontFamily: 'monospace',
          fontSize: 13,
          lineHeight: 1.5,
          maxHeight: 400,
          overflow: 'auto',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-all',
          color: 'var(--subtext1)',
        }}
      >
        {lines.length === 0 ? (
          <span style={{ color: 'var(--overlay1)' }}>
            {phase === 'streaming' || phase === 'connecting' ? 'Waiting for logs…' : 'No log lines received.'}
          </span>
        ) : (
          lines.map((line, i) => <div key={i}>{line}</div>)
        )}
      </div>
      <div role="status" style={{ fontSize: 11, color: phase === 'error' ? 'var(--red)' : 'var(--overlay1)', marginTop: 4 }}>
        {phase === 'connecting' && 'Connecting…'}
        {phase === 'streaming' && `Streaming (${lines.length} lines${lines.length >= MAX_LINES ? ', oldest dropped' : ''})`}
        {phase === 'reconnecting' && 'Connection lost, reconnecting…'}
        {phase === 'ended' && 'Stream ended.'}
        {phase === 'error' && `Stream error: ${detail}`}
      </div>
    </div>
  )
}
