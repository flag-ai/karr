import type { GPUInfo } from '../api/types'

function getUtilColor(percent: number): string {
  if (percent < 50) return 'var(--green)'
  if (percent < 80) return 'var(--yellow)'
  return 'var(--red)'
}

export default function GPUCard({ gpu }: { gpu: GPUInfo }) {
  const memUsed = gpu.memory_total_mib - gpu.memory_free_mib
  const memPercent = gpu.memory_total_mib > 0
    ? Math.round((memUsed / gpu.memory_total_mib) * 100)
    : 0

  return (
    <div style={{
      backgroundColor: 'var(--surface0)',
      borderRadius: 8,
      padding: 16,
      minWidth: 260,
    }}>
      <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>
        GPU {gpu.index}: {gpu.name}
      </div>
      <div style={{ fontSize: 12, color: 'var(--subtext0)', marginBottom: 12 }}>
        {gpu.vendor}
      </div>

      <div style={{ marginBottom: 8 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
          <span>Memory</span>
          <span>{memUsed} / {gpu.memory_total_mib} MiB ({memPercent}%)</span>
        </div>
        <div style={{ height: 8, backgroundColor: 'var(--surface1)', borderRadius: 4, overflow: 'hidden' }}>
          <div style={{
            height: '100%',
            width: `${memPercent}%`,
            backgroundColor: getUtilColor(memPercent),
            borderRadius: 4,
            transition: 'width 0.3s',
          }} />
        </div>
      </div>

      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
          <span>Utilization</span>
          <span>{gpu.utilization_percent}%</span>
        </div>
        <div style={{ height: 8, backgroundColor: 'var(--surface1)', borderRadius: 4, overflow: 'hidden' }}>
          <div style={{
            height: '100%',
            width: `${gpu.utilization_percent}%`,
            backgroundColor: getUtilColor(gpu.utilization_percent),
            borderRadius: 4,
            transition: 'width 0.3s',
          }} />
        </div>
      </div>
    </div>
  )
}
