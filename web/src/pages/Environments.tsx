import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import StatusBadge from '../components/StatusBadge'
import LogStream from '../components/LogStream'

export default function Environments() {
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [agentId, setAgentId] = useState('')
  const [image, setImage] = useState('')
  const [gpu, setGpu] = useState(false)
  const [error, setError] = useState('')
  const [logsEnvId, setLogsEnvId] = useState<string | null>(null)

  const { data: environments = [] } = useQuery({
    queryKey: ['environments'],
    queryFn: api.listEnvironments,
    refetchInterval: 5000,
  })

  const { data: agents = [] } = useQuery({
    queryKey: ['agents'],
    queryFn: api.listAgents,
  })

  const createMutation = useMutation({
    mutationFn: api.createEnvironment,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['environments'] })
      setName('')
      setImage('')
      setGpu(false)
      setError('')
    },
    onError: (err: Error) => setError(err.message),
  })

  const startMutation = useMutation({
    mutationFn: api.startEnvironment,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['environments'] }),
  })

  const stopMutation = useMutation({
    mutationFn: api.stopEnvironment,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['environments'] }),
  })

  const removeMutation = useMutation({
    mutationFn: api.removeEnvironment,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['environments'] }),
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    createMutation.mutate({ name, agent_id: agentId, image, gpu })
  }

  return (
    <div>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 24 }}>Environments</h1>

      <form onSubmit={handleSubmit} style={{
        backgroundColor: 'var(--surface0)',
        borderRadius: 8,
        padding: 20,
        marginBottom: 24,
        display: 'flex',
        gap: 12,
        flexWrap: 'wrap',
        alignItems: 'flex-end',
      }}>
        <div>
          <label style={{ display: 'block', fontSize: 12, marginBottom: 4, color: 'var(--subtext0)' }}>Name</label>
          <input value={name} onChange={e => setName(e.target.value)} placeholder="my-env" required />
        </div>
        <div>
          <label style={{ display: 'block', fontSize: 12, marginBottom: 4, color: 'var(--subtext0)' }}>Agent</label>
          <select value={agentId} onChange={e => setAgentId(e.target.value)} required>
            <option value="">Select agent...</option>
            {agents.map(a => (
              <option key={a.id} value={a.id}>{a.name}</option>
            ))}
          </select>
        </div>
        <div>
          <label style={{ display: 'block', fontSize: 12, marginBottom: 4, color: 'var(--subtext0)' }}>Image</label>
          <input value={image} onChange={e => setImage(e.target.value)} placeholder="nvidia/cuda:12.4.1-base-ubuntu22.04" required />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, paddingBottom: 4 }}>
          <input
            type="checkbox"
            id="gpu-check"
            checked={gpu}
            onChange={e => setGpu(e.target.checked)}
            style={{ width: 16, height: 16, padding: 0 }}
          />
          <label htmlFor="gpu-check" style={{ fontSize: 12, color: 'var(--subtext0)', cursor: 'pointer' }}>GPU</label>
        </div>
        <button type="submit" className="primary" disabled={createMutation.isPending}>
          {createMutation.isPending ? 'Creating...' : 'Create'}
        </button>
        {error && <div style={{ color: 'var(--red)', fontSize: 12, width: '100%' }}>{error}</div>}
      </form>

      <div style={{ display: 'grid', gap: 8 }}>
        {environments.map(env => (
          <div key={env.id} style={{
            backgroundColor: 'var(--surface0)',
            borderRadius: 8,
            padding: 16,
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontWeight: 600, marginBottom: 4 }}>{env.name}</div>
                <div style={{ fontSize: 12, color: 'var(--subtext0)' }}>
                  {env.image} {env.gpu && <span style={{ color: 'var(--green)' }}>(GPU)</span>}
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <StatusBadge status={env.status} />
                {env.status === 'stopped' && (
                  <button className="primary" onClick={() => startMutation.mutate(env.id)} style={{ fontSize: 12, padding: '4px 12px' }}>
                    Start
                  </button>
                )}
                {env.status === 'running' && (
                  <>
                    <button className="secondary" onClick={() => setLogsEnvId(logsEnvId === env.id ? null : env.id)} style={{ fontSize: 12, padding: '4px 12px' }}>
                      {logsEnvId === env.id ? 'Hide Logs' : 'Logs'}
                    </button>
                    <button className="danger" onClick={() => stopMutation.mutate(env.id)} style={{ fontSize: 12, padding: '4px 12px' }}>
                      Stop
                    </button>
                  </>
                )}
                {(env.status === 'stopped' || env.status === 'error') && (
                  <button className="danger" onClick={() => removeMutation.mutate(env.id)} style={{ fontSize: 12, padding: '4px 12px' }}>
                    Remove
                  </button>
                )}
              </div>
            </div>
            {logsEnvId === env.id && (
              <div style={{ marginTop: 12 }}>
                <LogStream environmentId={env.id} active={true} />
              </div>
            )}
          </div>
        ))}
        {environments.length === 0 && (
          <div style={{ color: 'var(--overlay1)', padding: 20 }}>No environments created</div>
        )}
      </div>
    </div>
  )
}
