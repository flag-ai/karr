import { useEffect, useState } from 'react'
import { copyText, formatRemaining } from '../lib/util'

interface Props {
  command: string
  expiresAt: string
}

export default function InstallCommand({ command, expiresAt }: Props) {
  const [copied, setCopied] = useState<'idle' | 'ok' | 'failed'>('idle')
  const [remaining, setRemaining] = useState(() => formatRemaining(expiresAt))

  useEffect(() => {
    const update = () => setRemaining(formatRemaining(expiresAt))
    update()
    const interval = setInterval(update, 1000)
    return () => clearInterval(interval)
  }, [expiresAt])

  const handleCopy = async () => {
    setCopied((await copyText(command)) ? 'ok' : 'failed')
    setTimeout(() => setCopied('idle'), 2000)
  }

  return (
    <div style={{ backgroundColor: 'var(--mantle)', borderRadius: 8, padding: 16, marginTop: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <span style={{ fontSize: 12, color: 'var(--subtext0)' }}>
          Run this command on the GPU host — expires in {remaining}
        </span>
        <button
          type="button"
          onClick={handleCopy}
          style={{
            fontSize: 12,
            padding: '4px 12px',
            backgroundColor: copied === 'ok' ? 'var(--green)' : copied === 'failed' ? 'var(--red)' : 'var(--surface1)',
            color: copied === 'idle' ? 'var(--text)' : 'var(--base)',
          }}
        >
          {copied === 'ok' ? 'Copied!' : copied === 'failed' ? 'Copy failed' : 'Copy'}
        </button>
      </div>
      <pre style={{ margin: 0, padding: 12, backgroundColor: 'var(--crust)', borderRadius: 4, fontSize: 13, overflowX: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-all', color: 'var(--text)' }}>
        {command}
      </pre>
    </div>
  )
}
