import { ReactElement } from 'react'
import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { vi } from 'vitest'
import { AuthProvider } from '../hooks/useAuth'

type Handler = (body: unknown) => { status: number; body?: unknown }
export type RouteHandlers = Record<string, Handler>

/**
 * Stubs global fetch. Keys are "METHOD /path", e.g. "GET /api/webhook-endpoints/".
 * Unmatched requests fail the test loudly.
 */
export function mockFetch(routes: RouteHandlers) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const method = (init?.method ?? 'GET').toUpperCase()
    const key = `${method} ${String(input)}`
    const handler = routes[key]
    if (!handler) throw new Error(`Unmocked request: ${key}`)
    const reqBody = typeof init?.body === 'string' ? JSON.parse(init.body) : undefined
    const { status, body } = handler(reqBody)
    return new Response(status === 204 ? null : JSON.stringify(body ?? {}), {
      status,
      headers: { 'Content-Type': 'application/json' },
    })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

export function loginAs(role: 'admin' | 'freelancer') {
  localStorage.setItem('token', 'test-token')
  localStorage.setItem('user', JSON.stringify({ id: 1, email: `${role}@test.test`, role }))
}

export function renderPage(ui: ReactElement, { path = '/', route = '/' } = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MemoryRouter initialEntries={[route]}>
          <Routes>
            <Route path={path} element={ui} />
            <Route path="/contracts" element={<p>Contracts page</p>} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  )
}
