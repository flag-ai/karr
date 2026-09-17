const statusColors: Record<string, string> = {
  online: 'var(--green)',
  running: 'var(--green)',
  claimed: 'var(--green)',
  offline: 'var(--overlay1)',
  stopped: 'var(--overlay1)',
  expired: 'var(--overlay1)',
  creating: 'var(--yellow)',
  pending: 'var(--yellow)',
  error: 'var(--red)',
  unauthorized: 'var(--red)',
}

export default function StatusBadge({ status, title }: { status: string; title?: string }) {
  const color = statusColors[status] ?? 'var(--overlay1)'
  return (
    <span title={title} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 500 }}>
      <span aria-hidden="true" style={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: color, display: 'inline-block' }} />
      {status}
    </span>
  )
}
