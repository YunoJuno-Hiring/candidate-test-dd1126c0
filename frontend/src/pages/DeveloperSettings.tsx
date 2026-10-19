import { useState, FormEvent } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  fetchWebhookEndpoints,
  createWebhookEndpoint,
  deleteWebhookEndpoint,
  updateWebhookEndpoint,
  sendTestEvent,
  describeTestResult,
  webhookErrorMessage,
} from '../api/webhooks'
import { WebhookEndpoint, WebhookEndpointCreated } from '../api/client'
import { useAuth } from '../hooks/useAuth'

// Shown once, straight after creation: the API never returns the full secret again.
function SecretBanner({ endpoint, onDismiss }: { endpoint: WebhookEndpointCreated; onDismiss: () => void }) {
  const [copied, setCopied] = useState(false)

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(endpoint.secret)
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }

  return (
    <div role="status" className="mt-4 bg-amber-50 border border-amber-200 rounded px-4 py-3 text-sm space-y-2">
      <p className="text-amber-900 font-medium">
        Endpoint saved. Copy the signing secret now — it won't be shown again.
      </p>
      <div className="flex items-center gap-2">
        <code data-testid="webhook-secret" className="flex-1 bg-white border border-amber-200 rounded px-2 py-1 font-mono text-xs break-all">
          {endpoint.secret}
        </code>
        <button
          type="button"
          onClick={handleCopy}
          className="text-xs border border-amber-300 rounded px-2 py-1 hover:bg-amber-100"
        >
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <p className="text-amber-800 text-xs">
        Verify each request by computing HMAC-SHA256 of <code>{'<t>.<raw body>'}</code> with this secret and
        comparing it to <code>v1</code> in the <code>YJ-Webhook-Signature</code> header. Dedupe on{' '}
        <code>YJ-Webhook-Id</code>.
      </p>
      <button type="button" onClick={onDismiss} className="text-xs text-amber-900 underline">
        I've saved the secret
      </button>
    </div>
  )
}

export default function DeveloperSettings() {
  const { isAdmin } = useAuth()
  const [url, setUrl] = useState('')
  const [description, setDescription] = useState('')
  const [created, setCreated] = useState<WebhookEndpointCreated | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [rowMessage, setRowMessage] = useState<{ id: number; ok: boolean; message: string } | null>(null)
  const queryClient = useQueryClient()

  const endpointsQuery = useQuery({
    queryKey: ['webhook-endpoints'],
    queryFn: fetchWebhookEndpoints,
    enabled: isAdmin,
  })

  function refreshEndpoints() {
    queryClient.invalidateQueries({ queryKey: ['webhook-endpoints'] })
  }

  const createMutation = useMutation({
    mutationFn: () => createWebhookEndpoint({ url, description }),
    onSuccess: (data) => {
      refreshEndpoints()
      setCreated(data)
      setErrorMsg(null)
      setUrl('')
      setDescription('')
    },
    onError: (err) => {
      setErrorMsg(webhookErrorMessage(err, 'Failed to save endpoint. Please try again.'))
    },
  })

  const toggleMutation = useMutation({
    mutationFn: (ep: WebhookEndpoint) => updateWebhookEndpoint(ep.id, { active: !ep.active }),
    onSuccess: refreshEndpoints,
    onError: (err, ep) => {
      setRowMessage({ id: ep.id, ok: false, message: webhookErrorMessage(err, 'Failed to update endpoint.') })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteWebhookEndpoint(id),
    onSuccess: refreshEndpoints,
    onError: (err, id) => {
      setRowMessage({ id, ok: false, message: webhookErrorMessage(err, 'Failed to delete endpoint.') })
    },
  })

  const testMutation = useMutation({
    mutationFn: (id: number) => sendTestEvent(id),
    onSuccess: (delivery, id) => {
      setRowMessage({ id, ...describeTestResult(delivery) })
      queryClient.invalidateQueries({ queryKey: ['webhook-deliveries', id] })
    },
    onError: (err, id) => {
      setRowMessage({ id, ok: false, message: webhookErrorMessage(err, 'Failed to send test event.') })
    },
  })

  if (!isAdmin) {
    return <Navigate to="/contracts" replace />
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setCreated(null)
    setErrorMsg(null)
    createMutation.mutate()
  }

  function handleDelete(ep: WebhookEndpoint) {
    if (window.confirm(`Delete the endpoint ${ep.url}? Its delivery log will be deleted too.`)) {
      setRowMessage(null)
      deleteMutation.mutate(ep.id)
    }
  }

  function handleTest(ep: WebhookEndpoint) {
    setRowMessage(null)
    testMutation.mutate(ep.id)
  }

  return (
    <div className="space-y-8 max-w-3xl">
      <div>
        <h1 className="text-xl font-semibold text-slate-900 mb-1">Developer settings</h1>
        <p className="text-slate-500 text-sm">
          Configure webhook endpoints to receive event notifications from YunoJuno. Each endpoint receives a signed{' '}
          <code className="bg-slate-100 px-1 rounded">timesheet.submitted</code> event when a freelancer submits hours.
        </p>
      </div>

      <div className="bg-white border border-slate-200 rounded-lg p-6">
        <h2 className="text-base font-medium text-slate-800 mb-4">Add webhook destination</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="webhook-url" className="block text-sm font-medium text-slate-700 mb-1">
              Destination URL
            </label>
            <input
              id="webhook-url"
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              required
              placeholder="https://example.com/webhook"
              className="w-full border border-slate-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            <p className="text-slate-400 text-xs mt-1">
              For local testing, use{' '}
              <code className="bg-slate-100 px-1 rounded">http://localhost:8027/hook</code>
            </p>
          </div>
          <div>
            <label htmlFor="webhook-description" className="block text-sm font-medium text-slate-700 mb-1">
              Description <span className="text-slate-400 font-normal">(optional)</span>
            </label>
            <input
              id="webhook-description"
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              maxLength={255}
              placeholder="e.g. Approval queue integration"
              className="w-full border border-slate-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <button
            type="submit"
            disabled={createMutation.isPending}
            className="bg-indigo-600 text-white text-sm px-4 py-2 rounded hover:bg-indigo-700 disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {createMutation.isPending ? 'Saving…' : 'Save endpoint'}
          </button>
        </form>

        {created && <SecretBanner endpoint={created} onDismiss={() => setCreated(null)} />}
        {errorMsg && (
          <div role="alert" className="mt-4 bg-red-50 border border-red-200 text-red-700 text-sm rounded px-3 py-2">
            {errorMsg}
          </div>
        )}
      </div>

      <div>
        <h2 className="text-base font-medium text-slate-800 mb-3">Configured endpoints</h2>

        {endpointsQuery.isLoading ? (
          <p className="text-slate-500 text-sm">Loading…</p>
        ) : endpointsQuery.isError ? (
          <p className="text-red-600 text-sm">Failed to load endpoints.</p>
        ) : !endpointsQuery.data || endpointsQuery.data.length === 0 ? (
          <div className="bg-white border border-slate-200 rounded-lg px-6 py-10 text-center">
            <p className="text-slate-500 text-sm">No webhook endpoints configured.</p>
          </div>
        ) : (
          <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 border-b border-slate-200">
                <tr>
                  <th className="text-left px-4 py-3 font-medium text-slate-600">URL</th>
                  <th className="text-left px-4 py-3 font-medium text-slate-600">Status</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {endpointsQuery.data.map((ep) => (
                  <tr key={ep.id} className="align-top">
                    <td className="px-4 py-3">
                      <Link
                        to={`/developers/endpoints/${ep.id}`}
                        className="text-indigo-700 hover:text-indigo-900 font-mono text-xs break-all"
                      >
                        {ep.url}
                      </Link>
                      {ep.description && <p className="text-slate-500 text-xs mt-1">{ep.description}</p>}
                      {rowMessage?.id === ep.id && (
                        <p className={`text-xs mt-1 ${rowMessage.ok ? 'text-green-700' : 'text-red-600'}`}>
                          {rowMessage.message}
                        </p>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${ep.active ? 'bg-green-100 text-green-800' : 'bg-slate-100 text-slate-500'}`}
                      >
                        {ep.active ? 'Active' : 'Disabled'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right whitespace-nowrap space-x-3">
                      <button
                        onClick={() => handleTest(ep)}
                        disabled={!ep.active || testMutation.isPending}
                        title={ep.active ? undefined : 'Enable the endpoint to send a test event'}
                        className="text-indigo-600 hover:text-indigo-800 text-xs disabled:opacity-50"
                      >
                        {testMutation.isPending && testMutation.variables === ep.id ? 'Sending…' : 'Send test'}
                      </button>
                      <button
                        onClick={() => toggleMutation.mutate(ep)}
                        disabled={toggleMutation.isPending}
                        className="text-slate-600 hover:text-slate-900 text-xs disabled:opacity-50"
                      >
                        {ep.active ? 'Disable' : 'Enable'}
                      </button>
                      <Link
                        to={`/developers/endpoints/${ep.id}`}
                        className="text-slate-600 hover:text-slate-900 text-xs"
                      >
                        Edit &amp; log
                      </Link>
                      <button
                        onClick={() => handleDelete(ep)}
                        disabled={deleteMutation.isPending}
                        className="text-red-600 hover:text-red-800 text-xs disabled:opacity-50"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
