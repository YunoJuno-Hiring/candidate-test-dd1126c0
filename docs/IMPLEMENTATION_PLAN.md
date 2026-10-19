# Implementation Plan

> Stage 01 document. Approved by the user on 2026-10-19. Implementation follows the slices below.

## Selected task
- **Task:** C — Fullstack: Outbound webhooks.
- **Reason for selection:** The user chose C over the assessment's recommendation (B). C covers both layers and centres on the integration boundary and failure reasoning that the brief evaluates. The extra scope risk is handled by doing the backend core first (slices 1–4) and keeping a written list of what was deliberately cut.

### Decisions confirmed with the user
| Decision | Choice | Why |
|---|---|---|
| System event | `timesheet.submitted` | It starts the approval clock, which in my experience is the most time-critical flow in contracting. Most companies expect timesheets approved within about two working days of submission, so hours submitted on Friday must be approved by Monday. Delivering the event at submission lets the company's own tools act on that deadline: remind the approver, track the deadline, or list pending approvals on Monday morning. It is also an asynchronous workflow boundary: the app never depends on those tools being up, because delivery runs through the outbox and worker. Billing and ERP consumers would want `timesheet.approved`, added later with the same mechanism. |
| Delivery mechanism | DB outbox + `manage.py deliver_webhooks` worker | Delivery rows commit in the same transaction as the timesheet write, so no event is lost and no event is sent for a rolled-back write. The worker runs outside the request path, so slow receivers never slow the API. No new services or backend dependencies. |
| HTTP client | Python standard library `urllib.request` | Enough for one POST with a timeout; avoids a new dependency. |
| Frontend tests | Add `vitest`, `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`, `jsdom` as dev dependencies | UI states such as "secret shown once", delete confirmation and the delivery log are worth testing directly. |
| Local receiver | Add `webhook-receiver` to `docker-compose.yml` | The README says it runs there, but the compose file lacks it. The smoke test needs it. |

## Requirements and acceptance criteria
- [x] **AC1 — CRUD and scoping.** A company admin can list, create, edit (URL, description, active) and delete their own webhook endpoints. Another company's endpoint returns 404. Freelancers get 403 and unauthenticated requests get 401 on every webhook route.
- [x] **AC2 — URL validation.** Only `http` and `https` URLs up to 500 characters are accepted. Invalid URLs return 400 with a field error.
- [x] **AC3 — Secret.** The server generates the secret (`whsec_` + `secrets.token_urlsafe(32)`). The full secret appears only in the create response. List and detail responses expose `secret_last4` only.
- [x] **AC4 — Event emission.** When a timesheet entry enters `submitted` (freelancer `POST /api/timesheets/`, or a `PATCH` that moves it from another status into `submitted`), one `WebhookDelivery` row is created for each **active** endpoint of the entry's company, in the same database transaction as the entry write. Inactive endpoints and other companies get nothing. A `PATCH` that leaves the status as `submitted`, or a request that fails validation, emits nothing.
- [x] **AC5 — Versioned payload.** `{"id": "evt_<uuid>", "type": "timesheet.submitted", "version": 1, "created_at": "<ISO 8601>", "data": {"timesheet_entry": {"id", "contract_id", "freelancer_id", "date", "hours", "status"}}}`. The event id is the same across retries and across endpoints for one event.
- [x] **AC6 — Signed request.** Headers: `Content-Type: application/json`, `YJ-Webhook-Id` (event id), `YJ-Webhook-Event`, `YJ-Webhook-Attempt`, `YJ-Webhook-Signature: t=<unix seconds>,v1=<hex HMAC-SHA256(secret, "<t>.<raw body>")>`.
- [x] **AC7 — Worker and retries.** `python manage.py deliver_webhooks` (`--once`, or a loop with `--interval`) sends due deliveries. Rows are claimed with `select_for_update(skip_locked=True)` so parallel workers do not double-send. Timeout is 5 seconds. A 2xx response marks the delivery `succeeded`. A non-2xx response, timeout or connection error records the attempt and schedules a retry after 1 min, 5 min, 30 min, 2 h, then 6 h. If attempt 6 fails, the delivery becomes `failed` (about 8.6 hours after the first attempt). If the endpoint was disabled before sending, the delivery becomes `cancelled` and no HTTP call is made.
- [x] **AC8 — Attempt log.** Every attempt is stored as a `WebhookDeliveryAttempt`: attempt number, response status (or null), error text, response body (truncated to 1 KB), duration in ms, timestamp.
- [x] **AC9 — Send test event.** `POST /api/webhook-endpoints/<id>/test/` creates a `webhook.test` delivery for that endpoint and makes attempt 1 inline, so the UI gets immediate feedback. A failure falls into the normal retry schedule. A disabled endpoint returns 400.
- [x] **AC10 — Delivery log API.** `GET /api/webhook-endpoints/<id>/deliveries/` returns the newest 50 deliveries with their attempts nested.
- [x] **AC11 — UI.** `/developers`: create form (URL, optional description); the secret appears once in a dismissible banner with a copy button; endpoint table with active toggle, Edit, Send test and Delete (with confirmation). `/developers/endpoints/:id`: edit form, Send test button and delivery log (event type, event id, status, attempts, last response code, timestamps) with expandable attempts and a 5-second auto-refresh. Every query has loading, empty and error states.
- [x] **AC12 — Local receiver.** `docker compose up` starts `webhook-receiver` on `localhost:8027`. The backend and worker run on the host, so the local URL is `http://localhost:8027/hook`; the UI hint is updated to match.

## Explicitly out of scope
Each item is recorded in `CANDIDATE_NOTES.md` with the reason.
- Celery, RQ or Redis.
- More than one event type, and per-endpoint event subscriptions.
- Secret rotation and encryption of the secret at rest. (It is stored in plain text because HMAC signing needs the raw value.)
- SSRF hardening: blocking private and loopback addresses and DNS rebinding. Local development needs `localhost`, so only the scheme is validated now.
- Auto-disabling endpoints after sustained failure, alerting, a manual "redeliver" button, and log retention.
- Fixing assessment findings 1–3 in `TimesheetDetailView.patch`. Because there is no state machine, a `PATCH` back into `submitted` re-emits the event; this is correct under AC4.
- Signature verification inside the receiver (it is a capture tool only).

## Current flow and integration points
- **Routes:** `backend/config/urls.py` includes `webhooks.urls` under `/api/`. `backend/webhooks/urls.py` currently uses `<str:pk>` so the stub id `'stub'` works; this changes to `<int:pk>`.
- **Stubs:** `backend/webhooks/views.py` returns `[]`, an echo of the URL, and 204, with only `IsAuthenticated`. `backend/webhooks/models.py` is empty; `backend/webhooks/migrations/` has only `__init__.py`.
- **Submit flow:** `frontend/src/pages/SubmitHours.tsx` → `POST /api/timesheets/` → `TimesheetListCreateView.post` (`backend/contracts/views.py`), which saves with `STATUS_SUBMITTED`.
- **Status change:** `PATCH /api/timesheets/<id>/` → `TimesheetDetailView.patch` (`backend/contracts/views.py`).
- **Developer settings UI:** `frontend/src/pages/DeveloperSettings.tsx` → `frontend/src/api/webhooks.ts` → `WebhookEndpoint {id, url, active}` in `frontend/src/api/client.ts`. The `/developers` nav link is admin-only in `frontend/src/components/Nav.tsx`.
- **Conventions:** plain `APIView` classes with inline `hasattr(user, 'company_admin')` checks; pytest tests in `<app>/tests/test_*.py` using fixtures from `backend/conftest.py`.

## Planned changes
| Slice | Files / area | Intended change | Tests / verification |
|---|---|---|---|
| 0 | `docs/IMPLEMENTATION_PLAN.md`, `docs/TEST_STRATEGY.md`, `docs/diagrams/request-flow.mmd`, `docs/diagrams/test-strategy.mmd`, `CANDIDATE_NOTES.md` | Plan, test strategy, Task C diagrams, decisions recorded | Review |
| 1 | `backend/webhooks/models.py`, `backend/webhooks/migrations/0001_initial.py`, `backend/webhooks/admin.py` | `WebhookEndpoint`, `WebhookDelivery`, `WebhookDeliveryAttempt` (see below) | `makemigrations --check`, model tests |
| 2 | `backend/webhooks/serializers.py`, `views.py`, `urls.py`, `tests/test_endpoints_api.py` | Admin-only, company-scoped CRUD; secret returned once; `test/` and `deliveries/` routes | API tests |
| 3 | `backend/webhooks/events.py`, `backend/webhooks/signing.py`, `backend/contracts/views.py`, `backend/webhooks/tests/test_events.py` | `build_payload()`, `emit_event()`; call it from timesheet POST and PATCH inside `transaction.atomic()` | Emission tests |
| 4 | `backend/webhooks/delivery.py`, `backend/webhooks/management/commands/deliver_webhooks.py`, `backend/webhooks/tests/test_delivery.py`, `Taskfile.dist.yml` | `attempt_delivery()` with an injectable sender, `process_due_deliveries()`, backoff table, give-up; `task worker` | Delivery tests with a mocked sender |
| 5 | `docker-compose.yml`, `DeveloperSettings.tsx` hint | Add the `webhook-receiver` service | `docker compose config`, curl to the receiver |
| 6 | `frontend/package.json`, `frontend/vite.config.ts` (test block), `frontend/src/test/setup.ts` | Add test dev dependencies and `"test": "vitest run"` | `tsc`, `vitest run` |
| 7 | `frontend/src/api/client.ts`, `frontend/src/api/webhooks.ts`, `frontend/src/pages/DeveloperSettings.tsx`, `frontend/src/pages/WebhookEndpointDetail.tsx` (new), `frontend/src/App.tsx`, `frontend/src/pages/*.test.tsx` | Types, API functions, UI per AC11 | `vitest`, `tsc`, `vite build` |
| 8 | `CANDIDATE_NOTES.md` | Final notes (Stage 05) | — |

### Data model
- `WebhookEndpoint`: `company` FK (CASCADE), `url` (URLField, max 500), `description` (blank), `secret`, `active` (default true), `created_at`, `updated_at`.
- `WebhookDelivery`: `endpoint` FK (CASCADE), `event_id` (UUID), `event_type`, `payload` (JSON), `status` (`pending` / `succeeded` / `failed` / `cancelled`), `attempt_count`, `next_attempt_at` (nullable), `last_response_code` (nullable), `created_at`, `updated_at`. Index on `(status, next_attempt_at)`.
- `WebhookDeliveryAttempt`: `delivery` FK (CASCADE), `attempt_number`, `response_status` (nullable), `error`, `response_body`, `duration_ms`, `created_at`.

### API
| Route | Methods |
|---|---|
| `/api/webhook-endpoints/` | GET, POST |
| `/api/webhook-endpoints/<int:pk>/` | GET, PATCH, DELETE |
| `/api/webhook-endpoints/<int:pk>/test/` | POST |
| `/api/webhook-endpoints/<int:pk>/deliveries/` | GET |

### Reuse
`api` and `ApiError` in `frontend/src/api/client.ts`; TanStack Query patterns and Tailwind classes from the existing pages; `StatusBadge` if it fits delivery status. Backend follows the `APIView` and inline permission style of `backend/contracts/views.py` and the `conftest.py` fixtures.

## Design decisions and trade-offs
- **Outbox in the same transaction (chosen)** vs. sending on `transaction.on_commit` from the request thread (rejected: blocks the request, and events are lost if the process dies before the send or retries are needed) vs. Celery/RQ with Redis (rejected for now: two new services and dependencies for one event type; the outbox table can feed a real queue later).
- **Worker claims rows with a lease:** inside a short transaction it selects due rows with `select_for_update(skip_locked=True)` and pushes `next_attempt_at` forward; the HTTP call happens outside the lock. A crashed worker's rows become due again when the lease expires.
- **Only the test event is sent inline**, for immediate feedback. Real events stay asynchronous.
- **Destination down for hours:** retries spread over about 8.6 hours, then `failed`. Rows are kept so a later redeliver feature can replay them.
- **Receiver idempotency:** consumers dedupe on `YJ-Webhook-Id`, which is stable across retries. The signed timestamp lets consumers reject replays older than a few minutes.
- **All non-2xx responses are retried**, including 4xx. Simple and predictable; treating 410 as "disable endpoint" is deferred.
- **Deleting an endpoint deletes its delivery log** (CASCADE). Soft delete is deferred.
- **Payload is a small snapshot with ids**, not nested objects, so the schema stays stable. `version: 1` allows later breaking changes.

## Risks and failure modes
| Risk | Mitigation / decision |
|---|---|
| Worker not running locally, so deliveries stay `pending` | `task worker`; the UI shows `pending` with the next attempt time; the test event is sent inline |
| Double send with concurrent workers | `select_for_update(skip_locked=True)` plus lease on `next_attempt_at` |
| Real network calls in tests | The sender is injected or monkeypatched; pytest makes no real HTTP calls |
| SSRF through user-supplied URLs | Scheme validation now; private-address blocking documented as a production requirement |
| Frontend dev dependencies while `pnpm` is not on the host | Use `corepack pnpm` and respect any existing lockfile; report exactly what changed |
| Scope overrun (largest task) | Backend core first (slices 1–4), then UI; stop and ask if time runs short |
| Assessment finding 1 (freelancer self-approve) | Not related to `timesheet.submitted`; left unchanged and documented |

## Rollout / migration considerations
- One new migration, `webhooks/0001_initial.py`, with new tables only. No change to existing tables, so it is safe to roll back by reverting the migration.
- A worker process is new in deployment. Without it, events queue but are not sent; no data is lost.

## Approval
Approved by the user on 2026-10-19. Implementation starts at slice 1.
