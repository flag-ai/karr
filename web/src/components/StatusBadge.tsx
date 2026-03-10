const statusColors: Record<string, string> = {
  online: 'var(--green)',
  running: 'var(--green)',
  offline: 'var(--overlay1)',
  stopped: 'var(--overlay1)',
  creating: 'var(--yellow)',
  error: 'var(--red)',
  removed: 'var(--surface2)',
}

export default function StatusBadge({ status }: { status: string }) {
  const color = statusColors[status] || 'var(--overlay1)'
  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 6,
      fontSize: 12,
      fontWeight: 500,
    }}>
      <span style={{
        width: 8,
        height: 8,
        borderRadius: '50%',
        backgroundColor: color,
        display: 'inline-block',
      }} />
      {status}
    </span>
  )
}
