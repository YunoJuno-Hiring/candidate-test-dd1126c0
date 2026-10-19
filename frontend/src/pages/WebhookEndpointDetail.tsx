import { useEffect, useState, FormEvent } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  describeTestResult,
  fetchWebhookDeliveries,
  fetchWebhookEndpoint,
  sendTestEvent,
  updateWebhookEndpoint,
  webhookErrorMessage,
} from '../api/webhooks'
import { WebhookDelivery, WebhookEndpoint } from '../api/client'
import { StatusBadge } from '../components/StatusBadge'
import { useAuth } from '../hooks/useAuth'

// The worker sends asynchronously, so poll while the page is open.
const DELIVERY_POLL_MS = 5_000

function formatTime(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString() : '—'
}

function EditForm({ endpoint }: { endpoint: WebhookEndpoint }) {
  const queryClient = useQueryClient()
  const [url, setUrl] = useState(endpoint.url)
  const [description, setDescription] = useState(endpoint.description)
  const [active, setActive] = useState(endpoint.active)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)

  // Keep the form in step if the endpoint is changed elsewhere (e.g. toggled on the list page).
  useEffect(() => {
    setUrl(endpoint.url)
    setDescription(endpoint.description)
    setActive(endpoint.active)
  }, [endpoint.url, endpoint.description, endpoint.active])

  const mutation = useMutation({
    mutationFn: () => updateWebhookEndpoint(endpoint.id, { url, description, active }),
    onSuccess: (updated) => {
      queryClient.setQueryData(['webhook-endpoint', endpoint.id], updated)
      queryClient.invalidateQueries({ queryKey: ['webhook-endpoints'] })
      setMessage({ ok: true, text: 'Changes saved.' })
    },
    onError: (err) => {
      setMessage({ ok: false, text: webhookErrorMessage(err, 'Failed to save changes.') })
    },
  })

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setMessage(null)
    mutation.mutate()
  }

  return (
    <form onSubmit={handleSubmit} className="bg-white border border-slate-200 rounded-lg p-6 space-y-4">
      <h2 className="text-base font-medium text-slate-800">Endpoint settings</h2>
      <div>
        <label htmlFor="edit-url" className="block text-sm font-medium text-slate-700 mb-1">
          Destination URL
        </label>
        <input
          id="edit-url"
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          required
          className="w-full border border-slate-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
      </div>
      <div>
        <label htmlFor="edit-description" className="block text-sm font-medium text-slate-700 mb-1">
          Description
        </label>
        <input
          id="edit-description"
          type="text"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          maxLength={255}
          className="w-full border border-slate-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
      </div>
      <label className="flex items-center gap-2 text-sm text-slate-700">
        <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
        Active — disabled endpoints receive no events, and queued retries are cancelled
      </label>
      <p className="text-slate-500 text-xs">
        Signing secret ends in <code className="bg-slate-100 px-1 rounded">…{endpoint.secret_last4}</code>
      </p>
      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={mutation.isPending}
          className="bg-indigo-600 text-white text-sm px-4 py-2 rounded hover:bg-indigo-700 disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {mutation.isPending ? 'Saving…' : 'Save changes'}
        </button>
        {message && (
          <span role={message.ok ? 'status' : 'alert'} className={`text-sm ${message.ok ? 'text-green-700' : 'text-red-600'}`}>
            {message.text}
          </span>
        )}
      </div>
    </form>
  )
}

function AttemptRows({ delivery }: { delivery: WebhookDelivery }) {
  if (delivery.attempts.length === 0) {
    return <p className="text-slate-500 text-xs">Not attempted yet.</p>
  }
  return (
    <table className="w-full text-xs">
      <thead>
        <tr className="text-slate-500">
          <th className="text-left py-1 font-medium">Attempt</th>
          <th className="text-left py-1 font-medium">Time</th>
          <th className="text-left py-1 font-medium">Result</th>
          <th className="text-left py-1 font-medium">Duration</th>
        </tr>
      </thead>
      <tbody>
        {delivery.attempts.map((a) => (
          <tr key={a.attempt_number}>
            <td className="py-1">#{a.attempt_number}</td>
            <td className="py-1">{formatTime(a.created_at)}</td>
            <td className="py-1 font-mono">{a.response_status !== null ? `HTTP ${a.response_status}` : a.error}</td>
            <td className="py-1">{a.duration_ms} ms</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function DeliveryLog({ endpointId }: { endpointId: number }) {
  const [expanded, setExpanded] = useState<number | null>(null)
  const deliveriesQuery = useQuery({
    queryKey: ['webhook-deliveries', endpointId],
    queryFn: () => fetchWebhookDeliveries(endpointId),
    refetchInterval: DELIVERY_POLL_MS,
  })

  if (deliveriesQuery.isLoading) {
    return <p className="text-slate-500 text-sm">Loading deliveries…</p>
  }
  if (deliveriesQuery.isError) {
    return <p className="text-red-600 text-sm">Failed to load the delivery log.</p>
  }
  const deliveries = deliveriesQuery.data ?? []
  if (deliveries.length === 0) {
    return (
      <div className="bg-white border border-slate-200 rounded-lg px-6 py-10 text-center">
        <p className="text-slate-500 text-sm">No deliveries yet. Send a test event to check the endpoint.</p>
      </div>
    )
  }

  return (
    <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-slate-50 border-b border-slate-200">
          <tr>
            <th className="text-left px-4 py-3 font-medium text-slate-600">Event</th>
            <th className="text-left px-4 py-3 font-medium text-slate-600">Status</th>
            <th className="text-left px-4 py-3 font-medium text-slate-600">Attempts</th>
            <th className="text-left px-4 py-3 font-medium text-slate-600">Last response</th>
            <th className="text-left px-4 py-3 font-medium text-slate-600">Fired</th>
            <th className="text-left px-4 py-3 font-medium text-slate-600">Next retry</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {deliveries.map((d) => (
            <DeliveryRow
              key={d.id}
              delivery={d}
              expanded={expanded === d.id}
              onToggle={() => setExpanded(expanded === d.id ? null : d.id)}
            />
          ))}
        </tbody>
      </table>
    </div>
  )
}

function DeliveryRow({
  delivery,
  expanded,
  onToggle,
}: {
  delivery: WebhookDelivery
  expanded: boolean
  onToggle: () => void
}) {
  return (
    <>
      <tr className="hover:bg-slate-50">
        <td className="px-4 py-3">
          <button
            type="button"
            onClick={onToggle}
            aria-expanded={expanded}
            className="text-left focus:outline-none focus:ring-2 focus:ring-indigo-500 rounded"
          >
            <span className="font-mono text-xs text-indigo-700 hover:text-indigo-900">
              {expanded ? '▾' : '▸'} {delivery.event_type}
            </span>
            <span className="block font-mono text-[11px] text-slate-400">
              {String(delivery.payload.id ?? delivery.event_id)}
            </span>
          </button>
        </td>
        <td className="px-4 py-3">
          <StatusBadge status={delivery.status} />
        </td>
        <td className="px-4 py-3 text-slate-700">{delivery.attempt_count}</td>
        <td className="px-4 py-3 text-slate-700 font-mono text-xs">
          {delivery.last_response_code ?? (delivery.attempt_count > 0 ? 'no response' : '—')}
        </td>
        <td className="px-4 py-3 text-slate-500 text-xs">{formatTime(delivery.created_at)}</td>
        <td className="px-4 py-3 text-slate-500 text-xs">
          {delivery.status === 'pending' ? formatTime(delivery.next_attempt_at) : '—'}
        </td>
      </tr>
      {expanded && (
        <tr className="bg-slate-50">
          <td colSpan={6} className="px-4 py-3">
            <AttemptRows delivery={delivery} />
          </td>
        </tr>
      )}
    </>
  )
}

export default function WebhookEndpointDetail() {
  const { id } = useParams<{ id: string }>()
  const endpointId = Number(id)
  const { isAdmin } = useAuth()
  const queryClient = useQueryClient()
  const [testMessage, setTestMessage] = useState<{ ok: boolean; message: string } | null>(null)

  const endpointQuery = useQuery({
    queryKey: ['webhook-endpoint', endpointId],
    queryFn: () => fetchWebhookEndpoint(endpointId),
    enabled: isAdmin,
  })

  const testMutation = useMutation({
    mutationFn: () => sendTestEvent(endpointId),
    onSuccess: (delivery) => {
      setTestMessage(describeTestResult(delivery))
      queryClient.invalidateQueries({ queryKey: ['webhook-deliveries', endpointId] })
    },
    onError: (err) => {
      setTestMessage({ ok: false, message: webhookErrorMessage(err, 'Failed to send test event.') })
    },
  })

  if (!isAdmin) {
    return <Navigate to="/contracts" replace />
  }
  if (endpointQuery.isLoading) {
    return <p className="text-slate-500">Loading…</p>
  }
  if (endpointQuery.isError || !endpointQuery.data) {
    return (
      <div className="space-y-4">
        <Link to="/developers" className="text-indigo-600 hover:text-indigo-800 text-sm inline-block">
          ← Developer settings
        </Link>
        <div className="bg-red-50 border border-red-200 text-red-700 rounded px-4 py-3 text-sm">
          Webhook endpoint not found or you don't have access.
        </div>
      </div>
    )
  }

  const endpoint = endpointQuery.data

  return (
    <div className="space-y-8 max-w-4xl">
      <div className="flex items-start justify-between gap-4">
        <div>
          <Link to="/developers" className="text-indigo-600 hover:text-indigo-800 text-sm mb-2 inline-block">
            ← Developer settings
          </Link>
          <h1 className="text-xl font-semibold text-slate-900 font-mono break-all">{endpoint.url}</h1>
          {endpoint.description && <p className="text-slate-500 text-sm mt-1">{endpoint.description}</p>}
        </div>
        <div className="flex flex-col items-end gap-2">
          <button
            onClick={() => {
              setTestMessage(null)
              testMutation.mutate()
            }}
            disabled={!endpoint.active || testMutation.isPending}
            title={endpoint.active ? undefined : 'Enable the endpoint to send a test event'}
            className="bg-indigo-600 text-white text-sm px-4 py-2 rounded hover:bg-indigo-700 disabled:opacity-60 disabled:cursor-not-allowed whitespace-nowrap"
          >
            {testMutation.isPending ? 'Sending…' : 'Send test event'}
          </button>
          {testMessage && (
            <p role={testMessage.ok ? 'status' : 'alert'} className={`text-xs ${testMessage.ok ? 'text-green-700' : 'text-red-600'}`}>
              {testMessage.message}
            </p>
          )}
        </div>
      </div>

      <EditForm endpoint={endpoint} />

      <div>
        <h2 className="text-base font-medium text-slate-800 mb-1">Delivery log</h2>
        <p className="text-slate-500 text-xs mb-3">
          Newest 50 deliveries. Failed attempts are retried after 1 min, 5 min, 30 min, 2 h and 6 h, then marked
          failed. Select an event to see each attempt.
        </p>
        <DeliveryLog endpointId={endpointId} />
      </div>
    </div>
  )
}
