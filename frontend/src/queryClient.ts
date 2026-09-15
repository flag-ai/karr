import { QueryCache, QueryClient } from '@tanstack/react-query'
import { ApiError } from './api/client'
import type { QueryErrorDetail } from './components/Toast'

/** Build the app's QueryClient: 401s are left to the AuthGate, every other
 * failed query is announced to the ToastProvider through a window event. */
export function makeQueryClient(): QueryClient {
  return new QueryClient({
    queryCache: new QueryCache({
      onError: (err, query) => {
        if (err instanceof ApiError && err.status === 401) return
        const label = typeof query.queryKey[0] === 'string' ? query.queryKey[0] : 'data'
        const detail: QueryErrorDetail = { label, message: err.message }
        window.dispatchEvent(new CustomEvent<QueryErrorDetail>('karr:query-error', { detail }))
      },
    }),
    defaultOptions: {
      queries: {
        retry: (count, err) => !(err instanceof ApiError && err.status === 401) && count < 1,
        refetchOnWindowFocus: false,
      },
    },
  })
}
