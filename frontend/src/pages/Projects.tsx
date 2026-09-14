import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, describeError } from '../api/client'
import type { Project } from '../api/types'
import { useToast } from '../components/Toast'
import { useConfirm } from '../components/ConfirmDialog'

export default function Projects() {
  const queryClient = useQueryClient()
  const toast = useToast()
  const confirm = useConfirm()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
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
      void queryClient.invalidateQueries({ queryKey: ['projects'] })
      setName('')
      setDescription('')
    },
    onError: err => toast.error(`Create failed: ${describeError(err)}`),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: { name?: string; description?: string } }) =>
      api.updateProject(id, data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['projects'] })
      setEditingId(null)
    },
    onError: err => toast.error(`Update failed: ${describeError(err)}`),
  })

  const deleteMutation = useMutation({
    mutationFn: api.deleteProject,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['projects'] })
      toast.success('Project deleted')
    },
    onError: err => toast.error(`Delete failed: ${describeError(err)}`),
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    createMutation.mutate({ name: name.trim(), description: description.trim() })
  }

  const startEditing = (project: Project) => {
    setEditingId(project.id)
    setEditName(project.name)
    setEditDescription(project.description)
  }

  const saveEdit = (id: string) => {
    updateMutation.mutate({ id, data: { name: editName.trim(), description: editDescription.trim() } })
  }

  const remove = async (project: Project) => {
    const ok = await confirm({
      title: 'Delete project',
      message: `Delete "${project.name}"? Environments keep running but lose their project.`,
      confirmLabel: 'Delete',
    })
    if (ok) deleteMutation.mutate(project.id)
  }

  return (
    <div>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 24 }}>Projects</h1>

      <form onSubmit={handleSubmit} style={{ backgroundColor: 'var(--surface0)', borderRadius: 8, padding: 20, marginBottom: 24, display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <div>
          <label htmlFor="project-name" style={{ display: 'block', fontSize: 12, marginBottom: 4, color: 'var(--subtext0)' }}>Name</label>
          <input id="project-name" value={name} onChange={e => setName(e.target.value)} placeholder="my-project" required />
        </div>
        <div style={{ flex: 1, minWidth: 200 }}>
          <label htmlFor="project-description" style={{ display: 'block', fontSize: 12, marginBottom: 4, color: 'var(--subtext0)' }}>Description</label>
          <input id="project-description" value={description} onChange={e => setDescription(e.target.value)} placeholder="Project description" style={{ width: '100%' }} />
        </div>
        <button type="submit" className="primary" disabled={createMutation.isPending || !name.trim()}>
          {createMutation.isPending ? 'Creating…' : 'Create Project'}
        </button>
      </form>

      <div style={{ display: 'grid', gap: 8 }}>
        {projects.map(project => (
          <div key={project.id} style={{ backgroundColor: 'var(--surface0)', borderRadius: 8, padding: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            {editingId === project.id ? (
              <form
                onSubmit={e => { e.preventDefault(); saveEdit(project.id) }}
                style={{ display: 'flex', gap: 8, alignItems: 'center', flex: 1, marginRight: 12 }}
                aria-label={`Edit ${project.name}`}
              >
                <input aria-label="Name" value={editName} onChange={e => setEditName(e.target.value)} required style={{ width: 180 }} />
                <input aria-label="Description" value={editDescription} onChange={e => setEditDescription(e.target.value)} style={{ flex: 1 }} />
                <button type="submit" className="primary" disabled={updateMutation.isPending} style={{ fontSize: 12, padding: '4px 12px' }}>
                  Save
                </button>
                <button type="button" className="secondary" onClick={() => setEditingId(null)} style={{ fontSize: 12, padding: '4px 12px' }}>
                  Cancel
                </button>
              </form>
            ) : (
              <>
                <div>
                  <div style={{ fontWeight: 600, marginBottom: 4 }}>{project.name}</div>
                  <div style={{ fontSize: 12, color: 'var(--subtext0)' }}>{project.description}</div>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button type="button" className="secondary" onClick={() => startEditing(project)} style={{ fontSize: 12, padding: '4px 12px' }}>
                    Edit
                  </button>
                  <button type="button" className="danger" onClick={() => void remove(project)} disabled={deleteMutation.isPending} style={{ fontSize: 12, padding: '4px 12px' }}>
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
