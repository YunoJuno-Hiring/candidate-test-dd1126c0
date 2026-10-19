# Test Strategy

## Principles
- Follow the repository's existing test frameworks and conventions.
- Test observable behaviour rather than implementation details.
- Prefer focused tests for validation, permissions, edge cases, and failures.
- Do not claim coverage without running a coverage tool and recording the result.

## Baseline
Recorded in `docs/ASSESSMENT.md` §2 (2026-10-17): pytest 41 passed; `manage.py check` clean; `makemigrations --check` no changes; `tsc --noEmit` and `vite build` passed; no frontend test runner and no linter configured.

## Selected task
- **Task:** C — Outbound webhooks (event `timesheet.submitted`, DB outbox + worker).
- **Critical user journey:** an admin adds an endpoint and copies the secret → sends a test event and sees it in the log → a freelancer submits hours → the worker delivers a signed `timesheet.submitted` event → the admin sees the attempt and response code in the log. If the receiver is down, retries appear in the log until success or give-up.
- **Relevant backend modules:** `backend/webhooks/` (models, serializers, views, urls, events, signing, delivery, management command); `backend/contracts/views.py` (emission points).
- **Relevant frontend modules:** `frontend/src/api/webhooks.ts`, `frontend/src/api/client.ts`, `frontend/src/pages/DeveloperSettings.tsx`, `frontend/src/pages/WebhookEndpointDetail.tsx`, `frontend/src/App.tsx`.

## Test matrix

| Scenario | Layer | Expected result | Test file |
|---|---|---|---|
| Create endpoint | Backend API | 201; response includes full `secret` starting `whsec_` | `webhooks/tests/test_endpoints_api.py` |
| List / detail hide secret | Backend API | Only `secret_last4` present | `test_endpoints_api.py` |
| Edit URL, description, active | Backend API | 200; values persisted; secret unchanged | `test_endpoints_api.py` |
| Delete endpoint | Backend API | 204; row and its deliveries gone | `test_endpoints_api.py` |
| Invalid URL / `ftp://` scheme | Backend API | 400 with `url` error | `test_endpoints_api.py` |
| Other company's endpoint (GET/PATCH/DELETE/test/deliveries) | Backend API | 404 | `test_endpoints_api.py` |
| Freelancer on any webhook route | Backend API | 403 | `test_endpoints_api.py` |
| Unauthenticated | Backend API | 401 | `test_endpoints_api.py` |
| Freelancer submits entry | Backend events | One delivery per active endpoint of that company; payload matches schema v1 | `webhooks/tests/test_events.py` |
| Inactive endpoint / other company's endpoint | Backend events | No delivery created | `test_events.py` |
| PATCH draft → submitted | Backend events | Delivery created | `test_events.py` |
| PATCH submitted → submitted, submitted → approved | Backend events | No delivery | `test_events.py` |
| Submit rejected by validation (400) | Backend events | No delivery | `test_events.py` |
| Signature | Backend unit | Known secret, timestamp and body give the expected HMAC; header format `t=…,v1=…` | `webhooks/tests/test_delivery.py` |
| 2xx response | Backend delivery | `succeeded`; attempt row with status code and duration | `test_delivery.py` |
| 500 response | Backend delivery | Still `pending`; `next_attempt_at` = now + 1 min (time frozen) | `test_delivery.py` |
| Timeout / connection error | Backend delivery | Attempt with null status and error text; retry scheduled | `test_delivery.py` |
| Sixth failed attempt | Backend delivery | `failed`; no further attempts | `test_delivery.py` |
| Endpoint disabled before send | Backend delivery | `cancelled`; sender not called | `test_delivery.py` |
| Not-yet-due delivery | Backend delivery | Skipped by `process_due_deliveries` | `test_delivery.py` |
| Event id stable across retries | Backend delivery | Same `YJ-Webhook-Id` on every attempt | `test_delivery.py` |
| Management command `--once` | Backend delivery | Processes due rows and exits | `test_delivery.py` |
| Send test event | Backend API | Inline attempt recorded; response shows result; disabled endpoint gives 400 | `test_endpoints_api.py` |
| Delivery log | Backend API | Newest first, max 50, attempts nested | `test_endpoints_api.py` |
| Secret shown once | Frontend | Banner shows secret after create; gone after dismiss | `src/pages/DeveloperSettings.test.tsx` |
| Delete confirmation | Frontend | Cancelling the confirm makes no API call | `DeveloperSettings.test.tsx` |
| Empty / loading / error lists | Frontend | Correct state text rendered | `DeveloperSettings.test.tsx`, `WebhookEndpointDetail.test.tsx` |
| Delivery log rows | Frontend | Shows event type, status, attempt count, response code | `WebhookEndpointDetail.test.tsx` |
| Send test result | Frontend | Success or failure message shown | `WebhookEndpointDetail.test.tsx` |
| Regression | Backend | All 41 existing tests still pass | existing suite |

## Verification commands
Commands confirmed to work in Stage 00 (the host has no `uv`, `pnpm` or `task`):
- Backend tests: `docker run --rm -v "$PWD/backend:/app" -w /app -e DB_HOST=host.docker.internal ghcr.io/astral-sh/uv:python3.11-bookworm-slim uv run --frozen pytest -q`
- Django check: same container, `uv run --frozen python manage.py check`
- Migration drift: same container, `uv run --frozen python manage.py makemigrations --check --dry-run`
- Frontend types: `frontend/node_modules/.bin/tsc --noEmit`
- Frontend build: `frontend/node_modules/.bin/vite build`
- Frontend tests (after slice 6): `frontend/node_modules/.bin/vitest run`
- Compose: `docker compose config`

Exact commands and outcomes are recorded in `docs/REVIEW_REPORT.md`.

## Manual smoke test
Performed on 2026-10-19; results and deviations (closed-port outage, backoff skipped through the shell) are in `docs/REVIEW_REPORT.md`.
1. `docker compose up -d` (db, mailpit, webhook-receiver).
2. Migrate and seed; start the backend, the worker (`python manage.py deliver_webhooks`) and the frontend.
3. Log in as the seeded admin; on `/developers` add `http://localhost:8027/hook` and copy the secret.
4. Click "Send test"; confirm the request at `http://localhost:8027` and a 200 row in the delivery log.
5. Log in as the seeded freelancer; submit hours.
6. Confirm a `timesheet.submitted` request at the receiver with `YJ-Webhook-*` headers, and a `succeeded` row in the log.
7. Stop the receiver; submit hours again; confirm a failed attempt and a scheduled retry in the log.
8. Restart the receiver; confirm the retry succeeds with the same event id.
