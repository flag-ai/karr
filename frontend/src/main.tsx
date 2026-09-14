import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import AuthGate from './components/AuthGate'
import { ToastProvider } from './components/Toast'
import { ConfirmProvider } from './components/ConfirmDialog'
import { makeQueryClient } from './queryClient'
import './theme.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={makeQueryClient()}>
      <ToastProvider>
        <ConfirmProvider>
          <AuthGate>
            <BrowserRouter>
              <App />
            </BrowserRouter>
          </AuthGate>
        </ConfirmProvider>
      </ToastProvider>
    </QueryClientProvider>
  </StrictMode>,
)
