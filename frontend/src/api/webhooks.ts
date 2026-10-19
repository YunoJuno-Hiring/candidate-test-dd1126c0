import {
  api,
  ApiError,
  WebhookDelivery,
  WebhookEndpoint,
  WebhookEndpointCreated,
  WebhookEndpointInput,
} from './client'

export function fetchWebhookEndpoints(): Promise<WebhookEndpoint[]> {
  return api.get('/api/webhook-endpoints/')
}

export function fetchWebhookEndpoint(id: number): Promise<WebhookEndpoint> {
  return api.get(`/api/webhook-endpoints/${id}/`)
}

export function createWebhookEndpoint(input: WebhookEndpointInput): Promise<WebhookEndpointCreated> {
  return api.post('/api/webhook-endpoints/', input)
}

export function updateWebhookEndpoint(
  id: number,
  changes: Partial<WebhookEndpointInput>,
): Promise<WebhookEndpoint> {
  return api.patch(`/api/webhook-endpoints/${id}/`, changes)
}

export function deleteWebhookEndpoint(id: number): Promise<void> {
  return api.delete(`/api/webhook-endpoints/${id}/`)
}

/** Sends a webhook.test event; the first attempt runs inline, so the result is in the response. */
export function sendTestEvent(id: number): Promise<WebhookDelivery> {
  return api.post(`/api/webhook-endpoints/${id}/test/`, {})
}

export function fetchWebhookDeliveries(id: number): Promise<WebhookDelivery[]> {
  return api.get(`/api/webhook-endpoints/${id}/deliveries/`)
}

/** Best human-readable message from a failed webhook API call. */
export function webhookErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    const field = err.data?.url ?? err.data?.detail
    if (Array.isArray(field) && field.length > 0) return String(field[0])
    if (typeof field === 'string') return field
  }
  return fallback
}

/** One-line summary of a test delivery's first attempt. */
export function describeTestResult(delivery: WebhookDelivery): { ok: boolean; message: string } {
  if (delivery.status === 'succeeded') {
    return { ok: true, message: `Test event delivered (HTTP ${delivery.last_response_code}).` }
  }
  const attempt = delivery.attempts[delivery.attempts.length - 1]
  const reason = attempt?.response_status ? `HTTP ${attempt.response_status}` : attempt?.error || 'no response'
  return { ok: false, message: `Test event failed (${reason}). It will be retried automatically.` }
}
