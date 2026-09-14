import { useEffect, useRef, useState } from 'react'
import { api, authHeaders } from '../api/client'
import { readEvents, unescapeLine } from '../api/sse'

interface Props {
  environmentId: string
  active: boolean
}

export const MAX_LINES = 5000
const RECONNECT_BASE_MS = 1000
const RECONNECT_MAX_MS = 30000

type Phase = 'connecting' | 'streaming' | 'ended' | 'error' | 'reconnecting' | 'stopped'

/**
 * Relays the container log SSE stream (K-D2): reads it over fetch so the
 * bearer token can be sent, keeps at most MAX_LINES, unescapes the frames,
 * reconnects with backoff after a dropped connection, and stops cleanly on
 * `event: end` / `event: error`.
 */
export default function LogStream({ environmentId, active }: Props) {
  const [lines, setLines] = useState<string[]>([])
  const [phase, setPhase] = useState<Phase>('connecting')
  const [detail, setDetail] = useState('')
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!active) {
      setPhase('stopped')
      return
    }
    const controller = new AbortController()
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

    const connect = async (): Promise<void> => {
      setPhase(attempt === 0 ? 'connecting' : 'reconnecting')
      let resp: Response
      try {
        resp = await fetch(api.environmentLogsUrl(environmentId), {
          headers: { Accept: 'text/event-stream', ...authHeaders() },
          signal: controller.signal,
        })
      } catch {
        if (controller.signal.aborted) return
        scheduleReconnect()
        return
      }
      if (!resp.ok) {
        // 401/404/409 will not change on retry; show the server's message
        let message = `${resp.status} ${resp.statusText}`
        try {
          const body = (await resp.json()) as { error?: string }
          if (body.error) message = body.error
        } catch {
          // keep the status line
        }
        setDetail(message)
        setPhase('error')
        return
      }
      if (!resp.body) {
        setDetail('the server sent no stream')
        setPhase('error')
        return
      }
      attempt = 0
      setPhase('streaming')
      try {
        for await (const event of readEvents(resp.body, controller.signal)) {
          if (event.event === 'end') {
            setPhase('ended')
            return
          }
          if (event.event === 'error') {
            setDetail(event.data || 'stream failed')
            setPhase('error')
            return
          }
          append(unescapeLine(event.data))
        }
      } catch {
        // dropped mid-stream: fall through to reconnect
      }
      if (!controller.signal.aborted) scheduleReconnect()
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
  }, [environmentId, active])

  useEffect(() => {
    const el = containerRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [lines])

  return (
    <div>
      <div
        ref={containerRef}
        role="log"
        aria-live="polite"
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
      <div style={{ fontSize: 11, color: phase === 'error' ? 'var(--red)' : 'var(--overlay1)', marginTop: 4 }}>
        {phase === 'connecting' && 'Connecting…'}
        {phase === 'streaming' && `Streaming (${lines.length} lines${lines.length >= MAX_LINES ? ', oldest dropped' : ''})`}
        {phase === 'reconnecting' && 'Connection lost, reconnecting…'}
        {phase === 'ended' && 'Stream ended.'}
        {phase === 'error' && `Stream error: ${detail}`}
        {phase === 'stopped' && 'Stopped.'}
      </div>
    </div>
  )
}
