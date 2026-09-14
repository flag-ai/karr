import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, describeError } from '../api/client'
import type { ProvisionResponse } from '../api/types'
import StatusBadge from '../components/StatusBadge'
import InstallCommand from '../components/InstallCommand'
import { useToast } from '../components/Toast'
import { useConfirm } from '../components/ConfirmDialog'

export default function Agents() {
  const queryClient = useQueryClient()
  const toast = useToast()
  const confirm = useConfirm()
  const [label, setLabel] = useState('')
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
    onSuccess: data => {
      void queryClient.invalidateQueries({ queryKey: ['registrations'] })
      setProvision(data)
      setLabel('')
    },
    onError: err => toast.error(`Provisioning failed: ${describeError(err)}`),
  })

  const deleteMutation = useMutation({
    mutationFn: api.deleteAgent,
    onSuccess: () => {
      for (const key of ['agents', 'registrations', 'environments']) {
        void queryClient.invalidateQueries({ queryKey: [key] })
      }
      toast.success('Agent removed')
    },
    onError: err => toast.error(`Remove failed: ${describeError(err)}`),
  })

  const deleteRegMutation = useMutation({
    mutationFn: api.deleteRegistration,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['registrations'] }),
    onError: err => toast.error(`Cancel failed: ${describeError(err)}`),
  })

  const handleProvision = (e: React.FormEvent) => {
    e.preventDefault()
    setProvision(null)
    provisionMutation.mutate({ label: label.trim() })
  }

  const removeAgent = async (id: string, name: string) => {
    const ok = await confirm({
      title: 'Remove agent',
      message: `Remove "${name}" from KARR? Environments on it must be deleted first.`,
      confirmLabel: 'Remove',
    })
    if (ok) deleteMutation.mutate(id)
  }

  const cancelRegistration = async (id: string, regLabel: string) => {
    const ok = await confirm({
      title: 'Cancel registration',
      message: `Cancel the pending registration "${regLabel}"? Its install command stops working.`,
      confirmLabel: 'Cancel registration',
    })
    if (ok) deleteRegMutation.mutate(id)
  }

  const pendingRegs = registrations.filter(r => r.status === 'pending')

  return (
    <div>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 24 }}>Agents</h1>

      <section style={{ backgroundColor: 'var(--surface0)', borderRadius: 8, padding: 20, marginBottom: 24 }} aria-labelledby="install-heading">
        <h2 id="install-heading" style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>Install Agent</h2>
        <form onSubmit={handleProvision} style={{ display: 'flex', gap: 12, alignItems: 'flex-end' }}>
          <div style={{ flex: 1 }}>
            <label htmlFor="provision-label" style={{ display: 'block', fontSize: 12, marginBottom: 4, color: 'var(--subtext0)' }}>
              Label
            </label>
            <input
              id="provision-label"
              value={label}
              onChange={e => setLabel(e.target.value)}
              placeholder="gpu-host-1"
              maxLength={200}
              required
              style={{ width: '100%' }}
            />
          </div>
          <button type="submit" className="primary" disabled={provisionMutation.isPending || !label.trim()}>
            {provisionMutation.isPending ? 'Generating…' : 'Generate Install Command'}
          </button>
        </form>

        {provision && (
          <InstallCommand command={provision.install_command} expiresAt={provision.expires_at} />
        )}

        {pendingRegs.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <h3 style={{ fontSize: 13, fontWeight: 600, marginBottom: 8, color: 'var(--subtext1)' }}>
              Pending Registrations
            </h3>
            <div style={{ display: 'grid', gap: 6 }}>
              {pendingRegs.map(reg => (
                <div key={reg.id} style={{ backgroundColor: 'var(--mantle)', borderRadius: 6, padding: 10, display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 13 }}>
                  <div>
                    <span style={{ fontWeight: 500 }}>{reg.label}</span>
                    <span style={{ color: 'var(--subtext0)', marginLeft: 8 }}>
                      expires {new Date(reg.expires_at).toLocaleTimeString()}
                    </span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <StatusBadge status={reg.status} />
                    <button
                      type="button"
                      className="danger"
                      onClick={() => void cancelRegistration(reg.id, reg.label)}
                      disabled={deleteRegMutation.isPending}
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
      </section>

      <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>Registered Agents</h2>
      <div style={{ display: 'grid', gap: 8 }}>
        {agents.map(agent => (
          <div key={agent.id} style={{ backgroundColor: 'var(--surface0)', borderRadius: 8, padding: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontWeight: 600, marginBottom: 4 }}>{agent.name}</div>
              <div style={{ fontSize: 12, color: 'var(--subtext0)' }}>{agent.url}</div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <StatusBadge
                status={agent.status}
                title={agent.last_seen_at ? `last seen ${new Date(agent.last_seen_at).toLocaleString()}` : undefined}
              />
              <button
                type="button"
                className="danger"
                onClick={() => void removeAgent(agent.id, agent.name)}
                disabled={deleteMutation.isPending}
                style={{ fontSize: 12, padding: '4px 12px' }}
              >
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
