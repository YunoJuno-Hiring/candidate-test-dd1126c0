import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import DeveloperSettings from './DeveloperSettings'
import { loginAs, mockFetch, renderPage } from '../test/utils'
import { WebhookDelivery, WebhookEndpoint } from '../api/client'

const LIST = 'GET /api/webhook-endpoints/'

function endpoint(overrides: Partial<WebhookEndpoint> = {}): WebhookEndpoint {
  return {
    id: 1,
    url: 'https://hooks.example.test/yj',
    description: 'Approval queue',
    active: true,
    secret_last4: 'abcd',
    created_at: '2026-10-19T09:00:00Z',
    updated_at: '2026-10-19T09:00:00Z',
    ...overrides,
  }
}

function testDelivery(overrides: Partial<WebhookDelivery> = {}): WebhookDelivery {
  return {
    id: 10,
    event_id: 'e1',
    event_type: 'webhook.test',
    status: 'succeeded',
    attempt_count: 1,
    next_attempt_at: null,
    last_response_code: 200,
    created_at: '2026-10-19T09:00:00Z',
    updated_at: '2026-10-19T09:00:00Z',
    payload: { id: 'evt_e1' },
    attempts: [
      { attempt_number: 1, response_status: 200, response_body: '', error: '', duration_ms: 12, created_at: '2026-10-19T09:00:00Z' },
    ],
    ...overrides,
  }
}

function renderSettings() {
  return renderPage(<DeveloperSettings />, { path: '/developers', route: '/developers' })
}

describe('DeveloperSettings', () => {
  it('redirects non-admins away', async () => {
    loginAs('freelancer')
    mockFetch({})
    renderSettings()
    expect(await screen.findByText('Contracts page')).toBeInTheDocument()
  })

  it('shows loading, then the empty state', async () => {
    loginAs('admin')
    mockFetch({ [LIST]: () => ({ status: 200, body: [] }) })
    renderSettings()
    expect(screen.getByText('Loading…')).toBeInTheDocument()
    expect(await screen.findByText('No webhook endpoints configured.')).toBeInTheDocument()
  })

  it('shows an error when the list fails', async () => {
    loginAs('admin')
    mockFetch({ [LIST]: () => ({ status: 500 }) })
    renderSettings()
    expect(await screen.findByText('Failed to load endpoints.')).toBeInTheDocument()
  })

  it('shows the secret once after creating, and hides it when dismissed', async () => {
    loginAs('admin')
    let endpoints: WebhookEndpoint[] = []
    const fetchMock = mockFetch({
      [LIST]: () => ({ status: 200, body: endpoints }),
      'POST /api/webhook-endpoints/': (body) => {
        endpoints = [endpoint({ url: (body as { url: string }).url })]
        return { status: 201, body: { ...endpoints[0], secret: 'whsec_supersecretvalueabcd' } }
      },
    })
    const user = userEvent.setup()
    renderSettings()

    await user.type(screen.getByLabelText('Destination URL'), 'https://hooks.example.test/yj')
    await user.type(screen.getByLabelText(/Description/), 'Approval queue')
    await user.click(screen.getByRole('button', { name: 'Save endpoint' }))

    expect(await screen.findByTestId('webhook-secret')).toHaveTextContent('whsec_supersecretvalueabcd')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/webhook-endpoints/',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ url: 'https://hooks.example.test/yj', description: 'Approval queue' }),
      }),
    )
    // The refetched list never carries the secret.
    expect(await screen.findByRole('link', { name: 'https://hooks.example.test/yj' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: "I've saved the secret" }))
    expect(screen.queryByTestId('webhook-secret')).not.toBeInTheDocument()
    expect(screen.queryByText(/whsec_supersecretvalueabcd/)).not.toBeInTheDocument()
  })

  it('shows the API validation message when the URL is rejected', async () => {
    loginAs('admin')
    mockFetch({
      [LIST]: () => ({ status: 200, body: [] }),
      'POST /api/webhook-endpoints/': () => ({ status: 400, body: { url: ['URL must use http or https.'] } }),
    })
    const user = userEvent.setup()
    renderSettings()

    await user.type(screen.getByLabelText('Destination URL'), 'https://x.test/hook')
    await user.click(screen.getByRole('button', { name: 'Save endpoint' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('URL must use http or https.')
    expect(screen.queryByTestId('webhook-secret')).not.toBeInTheDocument()
  })

  it('does not delete when the confirmation is cancelled', async () => {
    loginAs('admin')
    const fetchMock = mockFetch({
      [LIST]: () => ({ status: 200, body: [endpoint()] }),
      'DELETE /api/webhook-endpoints/1/': () => ({ status: 204 }),
    })
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const user = userEvent.setup()
    renderSettings()

    await user.click(await screen.findByRole('button', { name: 'Delete' }))

    expect(confirm).toHaveBeenCalledWith(expect.stringContaining('https://hooks.example.test/yj'))
    expect(fetchMock).not.toHaveBeenCalledWith('/api/webhook-endpoints/1/', expect.objectContaining({ method: 'DELETE' }))
  })

  it('deletes after confirmation', async () => {
    loginAs('admin')
    let endpoints = [endpoint()]
    mockFetch({
      [LIST]: () => ({ status: 200, body: endpoints }),
      'DELETE /api/webhook-endpoints/1/': () => {
        endpoints = []
        return { status: 204 }
      },
    })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const user = userEvent.setup()
    renderSettings()

    await user.click(await screen.findByRole('button', { name: 'Delete' }))

    expect(await screen.findByText('No webhook endpoints configured.')).toBeInTheDocument()
  })

  it('toggles an endpoint off', async () => {
    loginAs('admin')
    let current = endpoint()
    const fetchMock = mockFetch({
      [LIST]: () => ({ status: 200, body: [current] }),
      'PATCH /api/webhook-endpoints/1/': (body) => {
        current = { ...current, ...(body as Partial<WebhookEndpoint>) }
        return { status: 200, body: current }
      },
    })
    const user = userEvent.setup()
    renderSettings()

    await user.click(await screen.findByRole('button', { name: 'Disable' }))

    expect(await screen.findByText('Disabled')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/webhook-endpoints/1/',
      expect.objectContaining({ method: 'PATCH', body: JSON.stringify({ active: false }) }),
    )
    expect(screen.getByRole('button', { name: 'Send test' })).toBeDisabled()
  })

  it('reports a successful and a failed test event', async () => {
    loginAs('admin')
    let next = testDelivery()
    mockFetch({
      [LIST]: () => ({ status: 200, body: [endpoint()] }),
      'POST /api/webhook-endpoints/1/test/': () => ({ status: 201, body: next }),
    })
    const user = userEvent.setup()
    renderSettings()

    await user.click(await screen.findByRole('button', { name: 'Send test' }))
    expect(await screen.findByText('Test event delivered (HTTP 200).')).toBeInTheDocument()

    next = testDelivery({
      status: 'pending',
      last_response_code: null,
      attempts: [
        { attempt_number: 1, response_status: null, response_body: '', error: 'Connection error: refused', duration_ms: 3, created_at: '2026-10-19T09:00:00Z' },
      ],
    })
    await user.click(screen.getByRole('button', { name: 'Send test' }))
    await waitFor(() =>
      expect(
        screen.getByText('Test event failed (Connection error: refused). It will be retried automatically.'),
      ).toBeInTheDocument(),
    )
  })
})
