import { render } from '@testing-library/react'
import type { ReactNode } from 'react'
import { QueryClientProvider } from '@tanstack/react-query'
import { makeQueryClient } from '../queryClient'
import { MemoryRouter } from 'react-router-dom'
import { ToastProvider } from '../components/Toast'
import { ConfirmProvider } from '../components/ConfirmDialog'

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

export function noContent(): Response {
  return new Response(null, { status: 204 })
}

export function renderApp(ui: ReactNode, route = '/') {
  const client = makeQueryClient()
  client.setDefaultOptions({ queries: { retry: false, refetchOnWindowFocus: false } })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <ConfirmProvider>
          <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
        </ConfirmProvider>
      </ToastProvider>
    </QueryClientProvider>,
  )
}
