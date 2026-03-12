import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import StatusBadge from '../components/StatusBadge'

export default function Agents() {
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [token, setToken] = useState('')
  const [error, setError] = useState('')

  const { data: agents = [] } = useQuery({
    queryKey: ['agents'],
    queryFn: api.listAgents,
  })

  const createMutation = useMutation({
    mutationFn: api.createAgent,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      setName('')
      setUrl('')
      setToken('')
      setError('')
    },
    onError: (err: Error) => setError(err.message),
  })

  const deleteMutation = useMutation({
    mutationFn: api.deleteAgent,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['agents'] }),
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    createMutation.mutate({ name, url, token })
  }

  return (
    <div>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 24 }}>Agents</h1>

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
          <input value={name} onChange={e => setName(e.target.value)} placeholder="gpu-host-1" required />
        </div>
        <div>
          <label style={{ display: 'block', fontSize: 12, marginBottom: 4, color: 'var(--subtext0)' }}>URL</label>
          <input value={url} onChange={e => setUrl(e.target.value)} placeholder="http://host:7777" required />
        </div>
        <div>
          <label style={{ display: 'block', fontSize: 12, marginBottom: 4, color: 'var(--subtext0)' }}>Token</label>
          <input value={token} onChange={e => setToken(e.target.value)} type="password" placeholder="bearer token" />
        </div>
        <button type="submit" className="primary" disabled={createMutation.isPending}>
          {createMutation.isPending ? 'Adding...' : 'Add Agent'}
        </button>
        {error && <div style={{ color: 'var(--red)', fontSize: 12, width: '100%' }}>{error}</div>}
      </form>

      <div style={{ display: 'grid', gap: 8 }}>
        {agents.map(agent => (
          <div key={agent.id} style={{
            backgroundColor: 'var(--surface0)',
            borderRadius: 8,
            padding: 16,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}>
            <div>
              <div style={{ fontWeight: 600, marginBottom: 4 }}>{agent.name}</div>
              <div style={{ fontSize: 12, color: 'var(--subtext0)' }}>{agent.url}</div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <StatusBadge status={agent.status} />
              <button className="danger" onClick={() => deleteMutation.mutate(agent.id)} style={{ fontSize: 12, padding: '4px 12px' }}>
                Remove
              </button>
            </div>
          </div>
        ))}
        {agents.length === 0 && (
          <div style={{ color: 'var(--overlay1)', padding: 20 }}>No agents registered</div>
        )}
      </div>
    </div>
  )
}
