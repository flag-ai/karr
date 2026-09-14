import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Agent } from '../api/types'
import StatusBadge from '../components/StatusBadge'
import GPUCard from '../components/GPUCard'

export function AgentCard({ agent }: { agent: Agent }) {
  const online = agent.status === 'online'
  const { data: snapshot } = useQuery({
    queryKey: ['agentStatus', agent.id],
    queryFn: () => api.getAgentStatus(agent.id),
    refetchInterval: 10000,
    enabled: online,
  })
  const status = online ? snapshot : undefined // never show stale numbers beside "offline"

  const system = status?.system?.system
  const disk = status?.system?.disk
  const gpus = status?.gpu?.gpus ?? [] // K-D17: BONNIE sends `gpus: null` without a GPU

  return (
    <div style={{ backgroundColor: 'var(--surface0)', borderRadius: 8, padding: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <h3 style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>{agent.name}</h3>
        <StatusBadge status={agent.status} />
      </div>
      <div style={{ fontSize: 12, color: 'var(--subtext0)', marginBottom: 12 }}>{agent.url}</div>

      {system && (
        <div style={{ fontSize: 12, color: 'var(--subtext1)', marginBottom: 12 }}>
          <div>{system.hostname} — {system.cpu_model}</div>
          <div>{system.cpu_cores} cores, {Math.round((system.memory_mb ?? 0) / 1024)} GB RAM</div>
          {disk && (
            <div>
              Disk: {(disk.used_gb ?? 0).toFixed(1)} / {(disk.total_gb ?? 0).toFixed(1)} GB ({disk.used_percent})
            </div>
          )}
        </div>
      )}

      {gpus.length > 0 ? (
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          {gpus.map(gpu => (
            <GPUCard key={gpu.index} gpu={gpu} />
          ))}
        </div>
      ) : (
        status?.gpu && <div style={{ fontSize: 12, color: 'var(--overlay1)' }}>No GPUs reported</div>
      )}
    </div>
  )
}

export default function Dashboard() {
  const { data: agents = [], error: agentsError } = useQuery({
    queryKey: ['agents'],
    queryFn: api.listAgents,
    refetchInterval: 10000,
  })

  const { data: environments = [] } = useQuery({
    queryKey: ['environments'],
    queryFn: api.listEnvironments,
    refetchInterval: 10000,
  })

  const running = environments.filter(e => e.status === 'running')

  return (
    <div>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 24 }}>Dashboard</h1>

      {agentsError && (
        <div role="alert" style={{ color: 'var(--red)', fontSize: 13, marginBottom: 16 }}>
          Could not load agents: {agentsError.message}
        </div>
      )}

      <section style={{ marginBottom: 32 }} aria-labelledby="agents-heading">
        <h2 id="agents-heading" style={{ fontSize: 16, fontWeight: 600, marginBottom: 12, color: 'var(--subtext1)' }}>
          Agents ({agents.length})
        </h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(400px, 1fr))', gap: 16 }}>
          {agents.map(agent => (
            <AgentCard key={agent.id} agent={agent} />
          ))}
          {agents.length === 0 && (
            <div style={{ color: 'var(--overlay1)', padding: 20 }}>No agents registered</div>
          )}
        </div>
      </section>

      <section aria-labelledby="running-heading">
        <h2 id="running-heading" style={{ fontSize: 16, fontWeight: 600, marginBottom: 12, color: 'var(--subtext1)' }}>
          Running Environments ({running.length})
        </h2>
        {running.length === 0 ? (
          <div style={{ color: 'var(--overlay1)', padding: 20 }}>No running environments</div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 12 }}>
            {running.map(env => (
              <div key={env.id} style={{ backgroundColor: 'var(--surface0)', borderRadius: 8, padding: 16 }}>
                <div style={{ fontWeight: 600, marginBottom: 4 }}>{env.name}</div>
                <div style={{ fontSize: 12, color: 'var(--subtext0)' }}>{env.image}</div>
                <div style={{ marginTop: 8 }}><StatusBadge status={env.status} /></div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
