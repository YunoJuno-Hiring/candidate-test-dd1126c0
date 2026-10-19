import { describe, expect, it } from 'vitest'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import WebhookEndpointDetail from './WebhookEndpointDetail'
import { loginAs, mockFetch, renderPage } from '../test/utils'
import { WebhookDelivery, WebhookEndpoint } from '../api/client'

const ENDPOINT = 'GET /api/webhook-endpoints/1/'
const DELIVERIES = 'GET /api/webhook-endpoints/1/deliveries/'

const endpoint: WebhookEndpoint = {
  id: 1,
  url: 'https://hooks.example.test/yj',
  description: 'Approval queue',
  active: true,
  secret_last4: 'abcd',
  created_at: '2026-10-19T09:00:00Z',
  updated_at: '2026-10-19T09:00:00Z',
}

const retrying: WebhookDelivery = {
  id: 7,
  event_id: '5f1c',
  event_type: 'timesheet.submitted',
  status: 'pending',
  attempt_count: 2,
  next_attempt_at: '2026-10-19T09:10:00Z',
  last_response_code: 503,
  created_at: '2026-10-19T09:00:00Z',
  updated_at: '2026-10-19T09:05:00Z',
  payload: { id: 'evt_5f1c' },
  attempts: [
    { attempt_number: 1, response_status: null, response_body: '', error: 'Connection error: refused', duration_ms: 4, created_at: '2026-10-19T09:00:00Z' },
    { attempt_number: 2, response_status: 503, response_body: 'down', error: '', duration_ms: 31, created_at: '2026-10-19T09:01:00Z' },
  ],
}

function renderDetail() {
  return renderPage(<WebhookEndpointDetail />, {
    path: '/developers/endpoints/:id',
    route: '/developers/endpoints/1',
  })
}

describe('WebhookEndpointDetail', () => {
  it('shows not found for a missing or foreign endpoint', async () => {
    loginAs('admin')
    mockFetch({ [ENDPOINT]: () => ({ status: 404, body: { detail: 'Not found.' } }) })
    renderDetail()
    expect(await screen.findByText("Webhook endpoint not found or you don't have access.")).toBeInTheDocument()
  })

  it('shows the empty delivery log', async () => {
    loginAs('admin')
    mockFetch({
      [ENDPOINT]: () => ({ status: 200, body: endpoint }),
      [DELIVERIES]: () => ({ status: 200, body: [] }),
    })
    renderDetail()
    expect(await screen.findByText(/No deliveries yet/)).toBeInTheDocument()
    expect(screen.getByText('…abcd')).toBeInTheDocument()
  })

  it('shows an error when the delivery log fails', async () => {
    loginAs('admin')
    mockFetch({
      [ENDPOINT]: () => ({ status: 200, body: endpoint }),
      [DELIVERIES]: () => ({ status: 500 }),
    })
    renderDetail()
    expect(await screen.findByText('Failed to load the delivery log.')).toBeInTheDocument()
  })

  it('lists deliveries with status, attempts and response code, and expands attempts', async () => {
    loginAs('admin')
    mockFetch({
      [ENDPOINT]: () => ({ status: 200, body: endpoint }),
      [DELIVERIES]: () => ({ status: 200, body: [retrying] }),
    })
    const user = userEvent.setup()
    renderDetail()

    const toggle = await screen.findByRole('button', { name: /timesheet\.submitted/ })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    const row = toggle.closest('tr')!
    expect(within(row).getByText('evt_5f1c')).toBeInTheDocument()
    expect(within(row).getByText('pending')).toBeInTheDocument()
    expect(within(row).getByText('2')).toBeInTheDocument()
    expect(within(row).getByText('503')).toBeInTheDocument()
    expect(screen.queryByText('Connection error: refused')).not.toBeInTheDocument()

    // Keyboard: focus the toggle and press Enter.
    toggle.focus()
    await user.keyboard('{Enter}')

    expect(toggle).toHaveAttribute('aria-expanded', 'true')

    expect(screen.getByText('Connection error: refused')).toBeInTheDocument()
    expect(screen.getByText('HTTP 503')).toBeInTheDocument()
    expect(screen.getByText('#2')).toBeInTheDocument()
  })

  it('saves edits and shows the API error for a bad URL', async () => {
    loginAs('admin')
    let reject = true
    mockFetch({
      [ENDPOINT]: () => ({ status: 200, body: endpoint }),
      [DELIVERIES]: () => ({ status: 200, body: [] }),
      'PATCH /api/webhook-endpoints/1/': (body) =>
        reject
          ? { status: 400, body: { url: ['URL must use http or https.'] } }
          : { status: 200, body: { ...endpoint, ...(body as object) } },
    })
    const user = userEvent.setup()
    renderDetail()

    const urlInput = await screen.findByLabelText('Destination URL')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('URL must use http or https.')

    reject = false
    await user.clear(urlInput)
    await user.type(urlInput, 'https://moved.example.test/yj')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(await screen.findByText('Changes saved.')).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'https://moved.example.test/yj' })).toBeInTheDocument()
  })

  it('disables the test button for a disabled endpoint', async () => {
    loginAs('admin')
    mockFetch({
      [ENDPOINT]: () => ({ status: 200, body: { ...endpoint, active: false } }),
      [DELIVERIES]: () => ({ status: 200, body: [] }),
    })
    renderDetail()
    expect(await screen.findByRole('button', { name: 'Send test event' })).toBeDisabled()
  })
})
