import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'

export default function Projects() {
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [error, setError] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editName, setEditName] = useState('')
  const [editDescription, setEditDescription] = useState('')

  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: api.listProjects,
  })

  const createMutation = useMutation({
    mutationFn: api.createProject,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      setName('')
      setDescription('')
      setError('')
    },
    onError: (err: Error) => setError(err.message),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: { name?: string; description?: string } }) =>
      api.updateProject(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      setEditingId(null)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: api.deleteProject,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['projects'] }),
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    createMutation.mutate({ name, description })
  }

  const startEditing = (project: { id: string; name: string; description: string }) => {
    setEditingId(project.id)
    setEditName(project.name)
    setEditDescription(project.description)
  }

  const saveEdit = (id: string) => {
    updateMutation.mutate({ id, data: { name: editName, description: editDescription } })
  }

  return (
    <div>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 24 }}>Projects</h1>

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
          <input value={name} onChange={e => setName(e.target.value)} placeholder="my-project" required />
        </div>
        <div style={{ flex: 1, minWidth: 200 }}>
          <label style={{ display: 'block', fontSize: 12, marginBottom: 4, color: 'var(--subtext0)' }}>Description</label>
          <input value={description} onChange={e => setDescription(e.target.value)} placeholder="Project description" style={{ width: '100%' }} />
        </div>
        <button type="submit" className="primary" disabled={createMutation.isPending}>
          {createMutation.isPending ? 'Creating...' : 'Create Project'}
        </button>
        {error && <div style={{ color: 'var(--red)', fontSize: 12, width: '100%' }}>{error}</div>}
      </form>

      <div style={{ display: 'grid', gap: 8 }}>
        {projects.map(project => (
          <div key={project.id} style={{
            backgroundColor: 'var(--surface0)',
            borderRadius: 8,
            padding: 16,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}>
            {editingId === project.id ? (
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flex: 1, marginRight: 12 }}>
                <input value={editName} onChange={e => setEditName(e.target.value)} style={{ width: 180 }} />
                <input value={editDescription} onChange={e => setEditDescription(e.target.value)} style={{ flex: 1 }} />
                <button className="primary" onClick={() => saveEdit(project.id)} style={{ fontSize: 12, padding: '4px 12px' }}>
                  Save
                </button>
                <button className="secondary" onClick={() => setEditingId(null)} style={{ fontSize: 12, padding: '4px 12px' }}>
                  Cancel
                </button>
              </div>
            ) : (
              <>
                <div>
                  <div style={{ fontWeight: 600, marginBottom: 4 }}>{project.name}</div>
                  <div style={{ fontSize: 12, color: 'var(--subtext0)' }}>{project.description}</div>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button className="secondary" onClick={() => startEditing(project)} style={{ fontSize: 12, padding: '4px 12px' }}>
                    Edit
                  </button>
                  <button className="danger" onClick={() => deleteMutation.mutate(project.id)} style={{ fontSize: 12, padding: '4px 12px' }}>
                    Delete
                  </button>
                </div>
              </>
            )}
          </div>
        ))}
        {projects.length === 0 && (
          <div style={{ color: 'var(--overlay1)', padding: 20 }}>No projects created</div>
        )}
      </div>
    </div>
  )
}
