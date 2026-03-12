import { useEffect, useRef, useState } from 'react'

interface Props {
  environmentId: string
  active: boolean
}

export default function LogStream({ environmentId, active }: Props) {
  const [lines, setLines] = useState<string[]>([])
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!active) return

    setLines([])
    const source = new EventSource(`/api/v1/environments/${environmentId}/logs`)

    source.onmessage = (event) => {
      setLines(prev => [...prev, event.data])
    }

    source.onerror = () => {
      source.close()
    }

    return () => {
      source.close()
    }
  }, [environmentId, active])

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [lines])

  return (
    <div
      ref={containerRef}
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
        <span style={{ color: 'var(--overlay1)' }}>Waiting for logs...</span>
      ) : (
        lines.map((line, i) => <div key={i}>{line}</div>)
      )}
    </div>
  )
}
