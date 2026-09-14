import type { GPUInfo } from '../api/types'

function getUtilColor(percent: number): string {
  if (percent < 50) return 'var(--green)'
  if (percent < 80) return 'var(--yellow)'
  return 'var(--red)'
}

function clampPercent(value: number): number {
  if (!Number.isFinite(value)) return 0
  return Math.min(100, Math.max(0, Math.round(value)))
}

function Bar({ label, percent, detail }: { label: string; percent: number; detail: string }) {
  const value = clampPercent(percent)
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
        <span>{label}</span>
        <span>{detail}</span>
      </div>
      <div
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={value}
        style={{ height: 8, backgroundColor: 'var(--surface1)', borderRadius: 4, overflow: 'hidden' }}
      >
        <div style={{ height: '100%', width: `${value}%`, backgroundColor: getUtilColor(value), borderRadius: 4, transition: 'width 0.3s' }} />
      </div>
    </div>
  )
}

export default function GPUCard({ gpu }: { gpu: GPUInfo }) {
  const total = gpu.memory_total_mib ?? 0
  const free = gpu.memory_free_mib ?? 0
  const used = Math.max(0, total - free)
  const memPercent = total > 0 ? (used / total) * 100 : 0
  const util = gpu.utilization_percent ?? 0

  return (
    <div style={{ backgroundColor: 'var(--surface0)', borderRadius: 8, padding: 16, minWidth: 260 }}>
      <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>
        GPU {gpu.index}: {gpu.name}
      </div>
      <div style={{ fontSize: 12, color: 'var(--subtext0)', marginBottom: 12 }}>{gpu.vendor}</div>
      <Bar label="Memory" percent={memPercent} detail={`${used} / ${total} MiB (${clampPercent(memPercent)}%)`} />
      <Bar label="Utilization" percent={util} detail={`${clampPercent(util)}%`} />
    </div>
  )
}
