import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Agent } from '../api/types'
import StatusBadge from '../components/StatusBadge'
import GPUCard from '../components/GPUCard'

function AgentCard({ agent }: { agent: Agent }) {
  const { data: status } = useQuery({
    queryKey: ['agentStatus', agent.id],
    queryFn: () => api.getAgentStatus(agent.id),
    refetchInterval: 10000,
    enabled: agent.status === 'online',
  })

  return (
    <div style={{
      backgroundColor: 'var(--surface0)',
      borderRadius: 8,
      padding: 20,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <h3 style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>{agent.name}</h3>
        <StatusBadge status={agent.status} />
      </div>
      <div style={{ fontSize: 12, color: 'var(--subtext0)', marginBottom: 12 }}>{agent.url}</div>

      {status?.system && (
        <div style={{ fontSize: 12, color: 'var(--subtext1)', marginBottom: 12 }}>
          <div>{status.system.system.hostname} — {status.system.system.cpu_model}</div>
          <div>{status.system.system.cpu_cores} cores, {Math.round(status.system.system.memory_mb / 1024)} GB RAM</div>
          <div>Disk: {status.system.disk.used_gb.toFixed(1)} / {status.system.disk.total_gb.toFixed(1)} GB ({status.system.disk.used_percent})</div>
        </div>
      )}

      {status?.gpu && status.gpu.gpus.length > 0 && (
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          {status.gpu.gpus.map(gpu => (
            <GPUCard key={gpu.index} gpu={gpu} />
          ))}
        </div>
      )}
    </div>
  )
}

export default function Dashboard() {
  const { data: agents = [] } = useQuery({
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

      <div style={{ marginBottom: 32 }}>
        <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12, color: 'var(--subtext1)' }}>
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
      </div>

      <div>
        <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12, color: 'var(--subtext1)' }}>
          Running Environments ({running.length})
        </h2>
        {running.length === 0 ? (
          <div style={{ color: 'var(--overlay1)', padding: 20 }}>No running environments</div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 12 }}>
            {running.map(env => (
              <div key={env.id} style={{
                backgroundColor: 'var(--surface0)',
                borderRadius: 8,
                padding: 16,
              }}>
                <div style={{ fontWeight: 600, marginBottom: 4 }}>{env.name}</div>
                <div style={{ fontSize: 12, color: 'var(--subtext0)' }}>{env.image}</div>
                <div style={{ marginTop: 8 }}><StatusBadge status={env.status} /></div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
