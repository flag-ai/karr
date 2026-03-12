import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { ProvisionResponse } from '../api/types'
import StatusBadge from '../components/StatusBadge'
import InstallCommand from '../components/InstallCommand'

export default function Agents() {
  const queryClient = useQueryClient()
  const [label, setLabel] = useState('')
  const [error, setError] = useState('')
  const [provision, setProvision] = useState<ProvisionResponse | null>(null)

  const { data: agents = [] } = useQuery({
    queryKey: ['agents'],
    queryFn: api.listAgents,
    refetchInterval: 10000,
  })

  const { data: registrations = [] } = useQuery({
    queryKey: ['registrations'],
    queryFn: api.listRegistrations,
    refetchInterval: 10000,
  })

  const provisionMutation = useMutation({
    mutationFn: api.provisionAgent,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['registrations'] })
      setProvision(data)
      setLabel('')
      setError('')
    },
    onError: (err: Error) => setError(err.message),
  })

  const deleteMutation = useMutation({
    mutationFn: api.deleteAgent,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['agents'] }),
  })

  const deleteRegMutation = useMutation({
    mutationFn: api.deleteRegistration,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['registrations'] }),
  })

  const handleProvision = (e: React.FormEvent) => {
    e.preventDefault()
    setProvision(null)
    provisionMutation.mutate({ label })
  }

  const pendingRegs = registrations.filter(r => r.status === 'pending')

  return (
    <div>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 24 }}>Agents</h1>

      {/* Install Agent Section */}
      <div style={{
        backgroundColor: 'var(--surface0)',
        borderRadius: 8,
        padding: 20,
        marginBottom: 24,
      }}>
        <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>Install Agent</h2>
        <form onSubmit={handleProvision} style={{
          display: 'flex',
          gap: 12,
          alignItems: 'flex-end',
        }}>
          <div style={{ flex: 1 }}>
            <label style={{ display: 'block', fontSize: 12, marginBottom: 4, color: 'var(--subtext0)' }}>
              Label
            </label>
            <input
              value={label}
              onChange={e => setLabel(e.target.value)}
              placeholder="gpu-host-1"
              required
              style={{ width: '100%' }}
            />
          </div>
          <button type="submit" className="primary" disabled={provisionMutation.isPending}>
            {provisionMutation.isPending ? 'Generating...' : 'Generate Install Command'}
          </button>
        </form>
        {error && <div style={{ color: 'var(--red)', fontSize: 12, marginTop: 8 }}>{error}</div>}

        {provision && (
          <InstallCommand command={provision.install_command} expiresAt={provision.expires_at} />
        )}

        {/* Pending Registrations */}
        {pendingRegs.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <h3 style={{ fontSize: 13, fontWeight: 600, marginBottom: 8, color: 'var(--subtext1)' }}>
              Pending Registrations
            </h3>
            <div style={{ display: 'grid', gap: 6 }}>
              {pendingRegs.map(reg => (
                <div key={reg.id} style={{
                  backgroundColor: 'var(--mantle)',
                  borderRadius: 6,
                  padding: 10,
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  fontSize: 13,
                }}>
                  <div>
                    <span style={{ fontWeight: 500 }}>{reg.label}</span>
                    <span style={{ color: 'var(--subtext0)', marginLeft: 8 }}>
                      expires {new Date(reg.expires_at).toLocaleTimeString()}
                    </span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <StatusBadge status={reg.status} />
                    <button
                      className="danger"
                      onClick={() => deleteRegMutation.mutate(reg.id)}
                      style={{ fontSize: 11, padding: '2px 8px' }}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Registered Agents Section */}
      <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>Registered Agents</h2>
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
