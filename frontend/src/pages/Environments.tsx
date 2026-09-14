import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, describeError } from '../api/client'
import type { Environment } from '../api/types'
import StatusBadge from '../components/StatusBadge'
import LogStream from '../components/LogStream'
import { useToast } from '../components/Toast'
import { useConfirm } from '../components/ConfirmDialog'

export default function Environments() {
  const queryClient = useQueryClient()
  const toast = useToast()
  const confirm = useConfirm()
  const [name, setName] = useState('')
  const [agentId, setAgentId] = useState('')
  const [projectId, setProjectId] = useState('')
  const [image, setImage] = useState('')
  const [gpu, setGpu] = useState(false)
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

  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: api.listProjects,
  })

  const refresh = () => void queryClient.invalidateQueries({ queryKey: ['environments'] })

  const createMutation = useMutation({
    mutationFn: api.createEnvironment,
    onSuccess: () => {
      refresh()
      setName('')
      setImage('')
      setGpu(false)
    },
    onError: err => {
      refresh() // a failed create still leaves an `error` row (K-D3)
      toast.error(`Create failed: ${describeError(err)}`)
    },
  })

  const startMutation = useMutation({
    mutationFn: api.startEnvironment,
    onSuccess: refresh,
    onError: err => { refresh(); toast.error(`Start failed: ${describeError(err)}`) },
  })

  const stopMutation = useMutation({
    mutationFn: api.stopEnvironment,
    onSuccess: refresh,
    onError: err => { refresh(); toast.error(`Stop failed: ${describeError(err)}`) },
  })

  const removeMutation = useMutation({
    mutationFn: api.removeEnvironment,
    onSuccess: (_data, id) => {
      refresh()
      if (logsEnvId === id) setLogsEnvId(null)
      toast.success('Environment removed')
    },
    onError: err => { refresh(); toast.error(`Remove failed: ${describeError(err)}`) },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    createMutation.mutate({
      name: name.trim(),
      agent_id: agentId,
      image: image.trim(),
      gpu,
      ...(projectId ? { project_id: projectId } : {}),
    })
  }

  const stop = async (env: Environment) => {
    const ok = await confirm({ title: 'Stop environment', message: `Stop "${env.name}"? Running processes are terminated.`, confirmLabel: 'Stop' })
    if (ok) stopMutation.mutate(env.id)
  }

  const remove = async (env: Environment) => {
    const ok = await confirm({ title: 'Remove environment', message: `Remove "${env.name}" and its container? This cannot be undone.`, confirmLabel: 'Remove' })
    if (ok) removeMutation.mutate(env.id)
  }

  const busy = startMutation.isPending || stopMutation.isPending || removeMutation.isPending

  return (
    <div>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 24 }}>Environments</h1>

      <form onSubmit={handleSubmit} style={{ backgroundColor: 'var(--surface0)', borderRadius: 8, padding: 20, marginBottom: 24, display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <div>
          <label htmlFor="env-name" style={labelStyle}>Name</label>
          <input id="env-name" value={name} onChange={e => setName(e.target.value)} placeholder="my-env" required />
        </div>
        <div>
          <label htmlFor="env-agent" style={labelStyle}>Agent</label>
          <select id="env-agent" value={agentId} onChange={e => setAgentId(e.target.value)} required>
            <option value="">Select agent…</option>
            {agents.map(a => (
              <option key={a.id} value={a.id}>{a.name}{a.status !== 'online' ? ` (${a.status})` : ''}</option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="env-project" style={labelStyle}>Project</label>
          <select id="env-project" value={projectId} onChange={e => setProjectId(e.target.value)}>
            <option value="">None</option>
            {projects.map(p => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="env-image" style={labelStyle}>Image</label>
          <input id="env-image" value={image} onChange={e => setImage(e.target.value)} placeholder="nvidia/cuda:12.4.1-base-ubuntu22.04" required style={{ minWidth: 280 }} />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, paddingBottom: 4 }}>
          <input type="checkbox" id="gpu-check" checked={gpu} onChange={e => setGpu(e.target.checked)} style={{ width: 16, height: 16, padding: 0 }} />
          <label htmlFor="gpu-check" style={{ fontSize: 12, color: 'var(--subtext0)', cursor: 'pointer' }}>GPU</label>
        </div>
        <button type="submit" className="primary" disabled={createMutation.isPending || !name.trim() || !agentId || !image.trim()}>
          {createMutation.isPending ? 'Creating…' : 'Create'}
        </button>
      </form>

      <div style={{ display: 'grid', gap: 8 }}>
        {environments.map(env => (
          <div key={env.id} style={{ backgroundColor: 'var(--surface0)', borderRadius: 8, padding: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontWeight: 600, marginBottom: 4 }}>{env.name}</div>
                <div style={{ fontSize: 12, color: 'var(--subtext0)' }}>
                  {env.image} {env.gpu && <span style={{ color: 'var(--green)' }}>(GPU)</span>}
                </div>
                {env.status_message && (
                  <div style={{ fontSize: 12, color: 'var(--red)', marginTop: 4 }}>{env.status_message}</div>
                )}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <StatusBadge status={env.status} title={env.status_message} />
                {env.status === 'stopped' && (
                  <button type="button" className="primary" onClick={() => startMutation.mutate(env.id)} disabled={busy} style={btn}>
                    Start
                  </button>
                )}
                {env.container_id && env.status !== 'creating' && (
                  <button type="button" className="secondary" onClick={() => setLogsEnvId(logsEnvId === env.id ? null : env.id)} style={btn}>
                    {logsEnvId === env.id ? 'Hide Logs' : 'Logs'}
                  </button>
                )}
                {env.status === 'running' && (
                  <button type="button" className="danger" onClick={() => void stop(env)} disabled={busy} style={btn}>
                    Stop
                  </button>
                )}
                {(env.status === 'stopped' || env.status === 'error') && (
                  <button type="button" className="danger" onClick={() => void remove(env)} disabled={busy} style={btn}>
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

const labelStyle: React.CSSProperties = { display: 'block', fontSize: 12, marginBottom: 4, color: 'var(--subtext0)' }
const btn: React.CSSProperties = { fontSize: 12, padding: '4px 12px' }
