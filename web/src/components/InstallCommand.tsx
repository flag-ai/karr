import { useState, useEffect } from 'react'

interface Props {
  command: string
  expiresAt: string
}

export default function InstallCommand({ command, expiresAt }: Props) {
  const [copied, setCopied] = useState(false)
  const [remaining, setRemaining] = useState('')

  useEffect(() => {
    const update = () => {
      const diff = new Date(expiresAt).getTime() - Date.now()
      if (diff <= 0) {
        setRemaining('expired')
        return
      }
      const mins = Math.floor(diff / 60000)
      const secs = Math.floor((diff % 60000) / 1000)
      setRemaining(`${mins}m ${secs}s`)
    }
    update()
    const interval = setInterval(update, 1000)
    return () => clearInterval(interval)
  }, [expiresAt])

  const handleCopy = async () => {
    await navigator.clipboard.writeText(command)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div style={{
      backgroundColor: 'var(--mantle)',
      borderRadius: 8,
      padding: 16,
      marginTop: 12,
    }}>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 8,
      }}>
        <span style={{ fontSize: 12, color: 'var(--subtext0)' }}>
          Run this command on the GPU host — expires in {remaining}
        </span>
        <button
          onClick={handleCopy}
          style={{
            fontSize: 12,
            padding: '4px 12px',
            backgroundColor: copied ? 'var(--green)' : 'var(--surface1)',
            color: copied ? 'var(--base)' : 'var(--text)',
            border: 'none',
            borderRadius: 4,
            cursor: 'pointer',
          }}
        >
          {copied ? 'Copied!' : 'Copy'}
        </button>
      </div>
      <pre style={{
        margin: 0,
        padding: 12,
        backgroundColor: 'var(--crust)',
        borderRadius: 4,
        fontSize: 13,
        overflowX: 'auto',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-all',
        color: 'var(--text)',
      }}>
        {command}
      </pre>
    </div>
  )
}
