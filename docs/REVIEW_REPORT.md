# Review and Verification Report

## Summary
- **Selected task:** C — Fullstack outbound webhooks (`timesheet.submitted`, DB outbox + worker).
- **Review date:** 2026-10-19 (Stage 03 verification and Stage 04 review).
- **Overall status:** All automated checks pass (106 backend, 15 frontend). No regressions in the existing suite. API and browser smoke tests passed. Stage 04 found two Medium worker issues (F1, R1), both fixed with tests; Low items fixed or documented.

## Acceptance criteria

| Criterion | Evidence / implementation | Test or verification | Status |
|---|---|---|---|
| AC1 CRUD + scoping | `webhooks/views.py` (`_admin_company`, `_get_endpoint`) | `test_endpoints_api.py`: create/edit/delete, other company → 404 (GET/PATCH/DELETE/deliveries), freelancer → 403 on every route, anonymous → 401; smoke: freelancer token → 403 | Met |
| AC2 URL validation | `WebhookEndpointSerializer.validate_url`, `URLField(max_length=500)` | `test_create_rejects_invalid_url` (bad, `ftp://`, empty), `test_create_rejects_url_over_500_chars`, `test_edit_rejects_invalid_url`; frontend shows the API message | Met |
| AC3 Secret once | `generate_secret`, `WebhookEndpointCreatedSerializer` used only on create | `test_admin_creates_endpoint_and_sees_secret_once`, `test_list_and_detail_never_expose_secret`, `test_create_ignores_client_supplied_company_and_secret`; vitest secret banner test; browser: banner shown, list shows no secret | Met |
| AC4 Emission in same transaction | `contracts/views.py` POST and PATCH wrap save + `emit_timesheet_submitted` in `transaction.atomic()` | `test_events.py`: fan-out, inactive / other company, PATCH draft/rejected → submitted, no-op transitions, 400 emits nothing, rollback when the outbox write fails | Met |
| AC5 Versioned payload | `events.build_payload` (`version: 1`, `evt_<uuid>`) | `test_submit_queues_versioned_event_for_active_endpoint`, shared event id test; smoke payload captured at the receiver | Met |
| AC6 Signed request | `signing.py`, `delivery.build_headers` | HMAC known-answer test, header verification test; smoke: all `YJ-Webhook-*` headers present at the receiver | Met |
| AC7 Worker + retries | `delivery.py` (`claim_due_deliveries` with `skip_locked` + lease, `RETRY_DELAYS`, `MAX_ATTEMPTS = 6`), `deliver_webhooks` command | Outcome tests (2xx, 5xx, connection error), full backoff-to-failed test, disabled → cancelled, not-due skipped, lease test, `--once` command test; smoke outage and recovery | Met (see F1) |
| AC8 Attempt log | `WebhookDeliveryAttempt`, body truncated to 1 KB | Attempt assertions across `test_delivery.py`, `test_http_post_truncates_response_body` | Met |
| AC9 Send test event | `WebhookEndpointTestView`, `delivery.send_test_event` (leased, inline attempt) | Inline success, failure left for retry, disabled → 400, scoping 404, freelancer 403; smoke + browser: "Test event delivered (HTTP 200)." | Met |
| AC10 Delivery log API | `WebhookDeliveryListView` (newest 50, attempts prefetched) | `test_delivery_log_newest_first_with_nested_attempts`, `test_delivery_log_is_limited_to_50` | Met |
| AC11 UI | `DeveloperSettings.tsx`, `WebhookEndpointDetail.tsx`, route in `App.tsx` | 15 vitest tests (redirect, loading/empty/error, secret once, validation message, delete confirm cancel/accept, toggle, test result success/failure, detail not-found, log rows + expansion, edit save/error, disabled test button); browser check | Met |
| AC12 Local receiver | `docker-compose.yml` `webhook-receiver` service | `docker compose config`; container built, started, accepted `POST /hook` | Met |

## Commands actually run

All on 2026-10-19. Backend commands ran in a throwaway container because the host has no `uv`:
`docker run --rm -v "$PWD/backend:/app" -w /app -e DB_HOST=host.docker.internal -e UV_PROJECT_ENVIRONMENT=/tmp/venv -e PYTHONDONTWRITEBYTECODE=1 -v yj-uv-cache:/root/.cache/uv ghcr.io/astral-sh/uv:python3.11-bookworm-slim <cmd>` (shown below as `[uv]`).

| Command | Result | Notes |
|---|---|---|
| `[uv] uv run --frozen pytest -q` | **104 passed** | Baseline was 41 |
| `[uv] uv run --frozen pytest -q webhooks` | **63 passed** | New tests |
| `[uv] uv run --frozen pytest -q accounts contracts` | **41 passed** | Same count as the Stage 00 baseline: no regressions |
| `[uv] uv run --frozen python manage.py check` | No issues | |
| `[uv] uv run --frozen python manage.py makemigrations --check --dry-run` | No changes detected | `webhooks/0001_initial.py` matches the models |
| `frontend/node_modules/.bin/tsc --noEmit` | Passed | Includes test files |
| `frontend/node_modules/.bin/vitest run` | **15 passed** (2 files) | New runner. stderr shows React Router v7 future-flag warnings; these come from existing router config and are not failures |
| `frontend/node_modules/.bin/vite build` | Passed (JS 248.12 kB) | Baseline 235.29 kB |
| `docker compose config --quiet` | Passed | |
| `docker compose up -d --build webhook-receiver` + `curl -X POST localhost:8027/hook` | `{"received":true,"id":1}` | |
| `[uv] python manage.py migrate webhooks` | Applied `webhooks.0001_initial` to the local dev DB | Needed for the smoke test |
| `git diff --check` | Clean | |
| Not run: lint | — | No linter is configured in the repository (baseline) |
| Not run: coverage | — | No coverage tool configured; coverage is not claimed |

### Smoke test (performed)
Against the user's running dev server (`manage.py runserver` on :8000, `vite` on :3000), with the worker run on the host as `backend/.venv/bin/python manage.py deliver_webhooks --once`.

1. Admin created endpoint `http://localhost:8027/hook` through the API → 201 with `whsec_…` secret.
2. Send test → `webhook.test succeeded 200`.
3. Freelancer token on `/api/webhook-endpoints/` → 403.
4. Freelancer submitted hours → delivery `pending`, attempt 0. One worker pass → `succeeded`, 200. The receiver showed `YJ-Webhook-Id`, `-Event`, `-Attempt: 1`, `-Signature: t=…,v1=…` and the version 1 payload.
5. **Outage:** endpoint URL pointed at a closed port (`localhost:8099`), hours submitted, one worker pass → `pending`, attempt 1, error `Connection error: [Errno 61] Connection refused`, retry scheduled 1 minute later.
6. **Recovery:** URL restored and the pending row's `next_attempt_at` moved to now through `manage.py shell` (to skip the 1-minute wait) → worker pass → `succeeded`, attempts `[(1, None), (2, 200)]`, same event id; the receiver saw `YJ-Webhook-Attempt: 2`.
7. **Browser (Chrome, existing admin session):** `/developers` created a second endpoint and showed the one-time secret banner; "Send test" showed "Test event delivered (HTTP 200)."; `/developers/endpoints/1` showed the delivery log with 4 rows, and expanding the recovered delivery showed attempt #1 "Connection refused" and #2 "HTTP 200". No console errors.

Smoke caveats: stopping the receiver container did not simulate an outage because a separate host `node` receiver (the user's, pid 62011) also listens on :8027 and answers `localhost`; the closed-port approach was used instead. Smoke data was kept at the user's request (endpoints 1 and 2, timesheet entries for 2026-10-15/16/17, their deliveries).

## Edge cases and failure paths inspected

| Case | Behaviour | Evidence |
|---|---|---|
| Outbox write fails during submit | Entry rolled back too | `test_entry_is_rolled_back_if_queueing_the_event_fails` |
| Endpoint disabled after event queued | Delivery `cancelled`, no HTTP call | Test |
| Endpoint URL changed after queueing | New URL used | Test (bug found and fixed in Stage 02: the worker used a stale endpoint) |
| Endpoint deleted before send | Skipped | Test |
| Redirect response | Not followed; recorded as failed attempt (302) | `test_http_post_does_not_follow_redirects` |
| Concurrent workers | Second pass skips leased rows | `test_claimed_rows_are_leased_so_a_second_pass_skips_them` (single-process simulation; true multi-process concurrency not tested) |
| Worker dies after claiming | Row becomes due again after the 60 s lease | By design; covered by lease test only indirectly |
| Large response body | Truncated to 1 KB | Test |
| Receiver slow | 5 s timeout, recorded as error | Code path (`TimeoutError`); not exercised by a test |

### Re-run after Stage 04 fixes (2026-10-19)

| Command | Result |
|---|---|
| `[uv] uv run --frozen pytest -q` | **106 passed** (2 new worker tests) |
| Same two tests against a scratch copy of `backend/` with the pre-fix `process_due_deliveries` | **2 failed**, as expected |
| `[uv] manage.py check` / `makemigrations --check --dry-run` | No issues / no changes |
| `frontend/node_modules/.bin/tsc --noEmit` | Passed |
| `frontend/node_modules/.bin/vitest run` | **15 passed** |
| `frontend/node_modules/.bin/vite build` | Passed |
| `git diff --check` | Clean |

The browser and API smoke tests were not repeated after these fixes; the changed code paths are covered by the tests above.

## Findings

| Severity | Finding | Evidence | Resolution / follow-up |
|---|---|---|---|
| Medium (F1) | One unexpected exception inside `attempt_delivery` stops the whole worker loop. Example: an endpoint deleted *during* the HTTP call cascades its delivery away; the following attempt insert / delivery save then fails on the FK at commit with `IntegrityError`, which propagates out of `process_due_deliveries` and ends `deliver_webhooks`. | `backend/webhooks/delivery.py` `process_due_deliveries` has no per-delivery error handling. Reasoned from code; **not reproduced**. | Fixed in Stage 04 (see below). |
| Low (F2) | Inline "Send test" blocks the request for up to the 5 s timeout. | `WebhookEndpointTestView` | Accepted trade-off for immediate feedback; documented. |
| Low (F3) | A worker that crashes after sending but before recording the attempt resends with the same attempt number. | `attempt_delivery` records after the HTTP call | At-least-once delivery is expected; receivers dedupe on `YJ-Webhook-Id`. Document. |
| Info (F4) | Because of assessment finding 2 (writable `contract` on timesheet PATCH), a PATCH that moves an entry to another company's contract and into `submitted` emits to the new company. | `contracts/views.py` PATCH | Pre-existing gap, out of scope; documented. |
| Info (F5) | React Router v7 future-flag warnings in vitest stderr. | vitest output | Pre-existing router config; not changed. |

No baseline failures existed (Stage 00: 41 passed), and none were introduced.

### Stage 04 independent review (2026-10-19)
Scope: the full diff (`git diff --stat`: 21 tracked files, +1645/−134, plus new files under `backend/webhooks/` and `frontend/src/`). F1–F5 above are carried over; R-numbered items are new. User approved fixing F1, R1, R3 and R4 and documenting the rest (2026-10-19). Resolutions are in the last column.

| ID | Severity | Area | Finding | Evidence | Proposed resolution |
|---|---|---|---|---|---|
| F1 | Medium | Failure handling | One unexpected exception while processing a single delivery ends the whole worker (see above). | `backend/webhooks/delivery.py:164-169` — no per-delivery `try/except` | **Fixed.** `process_due_deliveries` catches and logs per delivery and continues; the row keeps its lease and is retried after 60 s. Test `test_unexpected_error_on_one_delivery_does_not_stop_the_batch`, confirmed to fail on the pre-fix code. |
| R1 | Medium | Concurrency | The claim leases a whole batch (up to 50 rows) for 60 s, but the rows are sent one after another, each taking up to the 5 s timeout. Rows late in a slow batch can pass their lease while still waiting, and a second worker can claim and send them too, creating duplicates. A single worker is not affected. This contradicts the "parallel workers do not double-send" claim in AC7 and the notes. | `delivery.py:36` (`CLAIM_LEASE = 60 s`), `:150-161` (batch claim), `:164-169` (sequential send) | **Fixed.** The worker claims one row at a time (`claim_due_deliveries(limit=1)` in a loop up to the batch size). Test `test_worker_claims_one_row_at_a_time_so_others_stay_claimable` simulates a second worker polling mid-send; confirmed to fail on the pre-fix code. |
| R2 | Low | Failure handling | `urllib`'s `timeout` applies to each socket operation, not to the whole request, so a receiver that trickles bytes can hold a send for longer than 5 s. Combined with R1's fix, the 60 s lease still bounds the duplicate window. | `delivery.py:69-79` | **Documented** in `CANDIDATE_NOTES.md`. A hard deadline needs a thread or another HTTP client. |
| R3 | Low | Test quality | `test_send_test_event_scoped_and_admin_only` takes an unused `freelancer_user` fixture and only checks scoping; the name overstates what it tests. | `backend/webhooks/tests/test_delivery.py:250` | **Fixed.** Renamed and unused fixture removed. |
| R4 | Low | Accessibility | Delivery rows expand only by mouse click on a `<tr>`; keyboard users cannot reach the attempt details. | `frontend/src/pages/WebhookEndpointDetail.tsx:199` | **Fixed.** The event cell is now a `<button aria-expanded>`; the vitest test expands it with the keyboard (Enter). |
| R5 | Info | Local setup | `task receiver` (host `node`) and the new compose service both bind :8027. Running both makes `localhost:8027` ambiguous (observed in the smoke test). | `Taskfile.dist.yml` `receiver`, `docker-compose.yml` | **Documented** in `CANDIDATE_NOTES.md`. |
| R6 | Info | Data | Concurrent PATCHes moving the same entry into `submitted` could each emit an event, because the previous status is read without a row lock. | `backend/contracts/views.py` PATCH | **Documented** in `CANDIDATE_NOTES.md`; needs the state machine from assessment finding 3. |

Checked with no finding:
- **Permissions and ownership:** every webhook route resolves the company from `request.user.company_admin` and never from the request body; ids from other companies return 404; freelancers get 403; `company` and `secret` in the create body are ignored (tested).
- **Secret handling:** only the create response includes the secret; `secret` is `editable=False`, so it is not in the serializer's writable fields or the Django admin form; the frontend keeps it only in component state until dismissed.
- **Input validation:** scheme and length validated server-side; the client-side `type="url"` is a convenience only.
- **Transactions:** emission is inside `transaction.atomic()` with the entry write (rollback tested); attempts and the delivery status update are written atomically; the HTTP call happens outside any transaction and outside the row lock.
- **Response rendering:** receiver response bodies and errors are rendered as React text, so no HTML injection.
- **API compatibility:** the endpoint id route changed from `<str:pk>` to `<int:pk>` and create now returns 201 instead of 200; the only client (`frontend/src/api/webhooks.ts`) was updated and checks `res.ok`.
- **Frontend states:** loading, empty, error and success states exist for the list, the detail page and the delivery log; mutations disable their buttons while pending; the admin-only redirect matches `NewContract.tsx`.
- **Unrelated changes:** none. `StatusBadge.tsx` gains four new status styles only; `vite.config.ts` switches `defineConfig` to `vitest/config` and adds a `test` block (dev server and build verified).

## Risks and limitations
- SSRF protection is limited to scheme validation; private/loopback addresses are allowed for local development.
- Secrets are stored in plain text; no rotation.
- Multi-worker concurrency is reasoned and unit-tested in one process only.
- Timeout path has no automated test.
- The UI was checked in Chrome with an existing admin session only; the freelancer redirect was verified by vitest, not in the browser.

## Diff hygiene
- `git diff --check`: clean.
- `git status` reviewed: changes are limited to `backend/webhooks/`, `backend/contracts/views.py` (emission only), `frontend/` (webhook pages, API, types, `StatusBadge` styles, test setup, `package.json`, `pnpm-lock.yaml`, `vite.config.ts`), `docker-compose.yml`, `Taskfile.dist.yml`, `docs/`, `CANDIDATE_NOTES.md`.
- Unrelated changes checked: pre-existing `.gitignore` edit and untracked `services/webhook-receiver/package-lock.json` were left untouched.

## Final reviewer recommendation
Functionally complete against AC1–AC12, with tests at every layer and a passing end-to-end smoke. F1, R1, R3 and R4 are fixed and covered by tests; F2–F5, R2, R5 and R6 are documented in `CANDIDATE_NOTES.md`. Ready for Stage 05 finalisation.
