# Candidate Notes

## Initial findings (Stage 00 assessment)
These issues were found while assessing the repository, before any task was selected. Full evidence is in `docs/ASSESSMENT.md`.

1. **The timesheet update endpoint has three gaps.** These are in `PATCH /api/timesheets/<id>/`, which is `TimesheetDetailView.patch` in `backend/contracts/views.py` together with `TimesheetEntrySerializer` in `backend/contracts/serializers.py`. I confirmed each gap with throwaway tests that I ran outside the repository:
   - A freelancer can approve their own entry. `PATCH {"status": "approved"}` returns 200 and the entry is approved.
   - An admin can move an entry onto another company's contract, because the `contract` field is writable against all contracts.
   - Status changes follow no rules. An approved entry can go back to `draft` with new hours.
2. **The webhook receiver is not in `docker-compose.yml`,** although the README says it runs there. It can only be started with `task receiver` or from its own Dockerfile in `services/webhook-receiver/`.
3. **The cost formula is ambiguous.** `Contract.daily_rate` is a daily rate and the brief says "hours × contract rate". However, `frontend/src/pages/ContractDetail.tsx:45` estimates cost as `hours × daily_rate / 8`.
4. **The billing and webhook stub endpoints only require `IsAuthenticated`,** so freelancers can call them too. Only the navigation UI restricts these pages to admins.

**What happened to each finding after selecting Task C:**
1. Deferred, as it is outside Task C. Two side effects on the new event are documented under known limitations.
2. Fixed: `webhook-receiver` was added to `docker-compose.yml`.
3. Not relevant to Task C, so left unchanged. It matters for Task A, Task B and the anomaly-detection idea.
4. Fixed for webhooks: every webhook route is now admin-only and company-scoped. The billing stubs (Task B) are unchanged.

## What I built and why
**Task C — outbound webhooks.** A company admin can create, edit, disable and delete webhook endpoints, send a test event, and inspect a delivery log (event, status, attempts, response code, next retry). The system delivers one real event, `timesheet.submitted`, signed and versioned, with retries.

My assessment (`docs/ASSESSMENT.md`) rated B the safest choice. I picked C because it exercises both layers and is all about the integration boundary and failure reasoning. I kept the scope under control by building the backend core first and keeping an explicit list of cuts.

**Why `timesheet.submitted`:** it starts the approval clock, which in my experience is the most time-critical flow in contracting. Most companies expect timesheets approved within about two working days of submission, so hours submitted on Friday must be approved by Monday. Delivering the event at submission lets the company's own tools act on that deadline: remind the approver, track the deadline, or list pending approvals on Monday morning. It is also an asynchronous workflow boundary: the app never depends on those tools being up, because delivery runs through the outbox and worker. Billing and ERP consumers would want `timesheet.approved`, added later with the same mechanism.

## Implementation notes
- **Transactional outbox plus worker.** One `WebhookDelivery` row per active endpoint is written in the same transaction as the timesheet entry, so events are never lost and never sent for rolled-back writes. `manage.py deliver_webhooks` (`task worker`) sends due rows. It claims them one at a time with `SELECT … FOR UPDATE SKIP LOCKED` and a 60-second lease, so parallel workers don't double-send and a crashed worker's row is retried. Slow receivers never slow the API. No queue or new backend dependency: Celery or RQ would add Redis for one event type, and the outbox can feed a queue later.
- **Retries:** after 1 m, 5 m, 30 m, 2 h and 6 h. The delivery is marked `failed` after attempt 6, about 8.6 hours after the first attempt, which covers an outage lasting hours. Rows are kept for a future redeliver feature. Every attempt is logged. Redirects are treated as failures, not followed. A disabled endpoint cancels its queued deliveries.
- **Signing and dedupe.** `YJ-Webhook-Signature: t=<unix>,v1=HMAC-SHA256(secret, "<t>.<body>")`; the timestamp lets receivers reject replays. `YJ-Webhook-Id` (the event id) is stable across retries, so receivers dedupe on it. The payload is `{id, type, version: 1, created_at, data}`.
- **Secret** generated server side and returned only in the create response; later responses show the last 4 characters.
- **"Send test"** makes its first attempt inline for immediate feedback; real events always go through the worker.
- **Permissions:** company admins only. Company comes from the user, never the request; other companies' ids return 404; freelancers get 403.
- **Also changed:** `webhook-receiver` added to `docker-compose.yml` (the README said it was there; it wasn't).
- **Deliberately cut:** SSRF protection beyond scheme validation (local development must post to `localhost`); secret rotation and encryption at rest; auto-disabling failing endpoints, alerting, redeliver, log retention; the existing timesheet `PATCH` gaps (self-approval, cross-company contract move, no state machine).
- **Known limitations:** delivery is at least once. The 5-second timeout applies per socket operation, not per request. "Send test" blocks its request for up to 5 seconds. Concurrent `PATCH`es into `submitted` could emit twice until timesheets get a state machine. Run either `task receiver` or the compose receiver, not both: they share port 8027.

## Testing and verification
- **Backend (pytest, house style):** 106 passed, of which 41 existing (unchanged count, no regressions) and 65 new. They cover CRUD, scoping, validation, secret-once, emission and rollback, signing, the retry schedule and give-up, cancellation, leasing and the worker. `http_post` runs against a real local HTTP server.
- **Frontend (vitest + Testing Library, newly added):** 15 passed: loading, empty and error states, secret-once banner, delete confirmation, toggle, test result, log expansion by keyboard, edit errors. `tsc` and `vite build` pass.
- **Other checks:** `manage.py check` and `makemigrations --check` are clean. There is no linter or coverage tool in the repo, so I don't claim either.
- **Manual end-to-end check** with the real receiver: test event, freelancer submit, worker delivery, an outage simulated with a closed port, then recovery on attempt 2 with the same event id. The UI was also checked in Chrome.
- **Bugs found and fixed:**
  - Found while testing: the worker used stale endpoint data, so a disable or URL edit after the delivery was loaded was missed.
  - Found in self-review: one exception could stop the whole worker loop.
  - Also from review: batch leases could expire mid-batch and allow double-sends.
  - Each fix has a test, and the last two tests fail on the old code. Details are in `docs/REVIEW_REPORT.md`.

## Workflow and AI assistance
I used Claude Code with a staged workflow (`WORKFLOW.md`, one command per stage): assess, plan, implement, verify, review, finalise. Each stage ended at an approval gate where I made the decisions: task, event, outbox vs queue, adding frontend test dependencies, and which review fixes to apply.

The AI explored the repository, drafted the plan and the tests, implemented in small slices, and reviewed its own diff. I verified everything by running the suites (backend in a throwaway `uv` container, since the host has no `uv`), the end-to-end smoke test and a browser check.

It was useful for breadth and for test coverage. Judgement still mattered:
- My first justification for `timesheet.submitted` named ERP and billing systems as consumers. The AI pointed out that those fit `timesheet.approved` better, because submitted hours can still be rejected. I narrowed the justification and noted `approved` as the follow-up event.
- The review stage caught a concurrency flaw in the first worker version.

## What I would do with four more hours
1. **SSRF protection:** resolve the host and block private, loopback and link-local addresses, with a development allowlist setting. This is required before production.
2. **Operations:** a manual "redeliver" button for failed deliveries, auto-disable an endpoint after N consecutive failures and notify its admins, and a retention command that prunes old logs.
3. **Secret rotation** with an overlap window: sign with both secrets until the old one expires.
4. **Per-endpoint event subscriptions,** plus `timesheet.approved` for billing and ERP consumers.
5. **Run the worker in `docker-compose`** and add a real multi-process concurrency test.

## Beyond this task: AI-assisted anomaly detection (idea, not built)
After finishing Task C, I explored flagging unusual timesheets for admins, for example 14 hours logged by someone who usually works 7.5. The full proposal is in `docs/AI_ANOMALY_DETECTION.md`. In short:
- **Detection is rules and statistics, not AI.** Hard limits, entries outside contract dates and duplicates across contracts are simple rules. Unusual days or weeks are a z-score against the freelancer's last 30 days, with an explicit "not enough history" result. Monthly cost spikes are a comparison against a trailing average, broken down by freelancer and extra hours.
- **The LLM only explains.** It turns findings that code already calculated into a short note and a weekly summary for the admin. It never calculates numbers or changes a status. Its output is schema-validated JSON, any number it mentions must appear in the evidence, and a template explanation is used if the call fails.
- **It fits the existing design.** Checks run on submit next to the `timesheet.submitted` emission. LLM explanations are filled in asynchronously by reusing the outbox and worker from this task. The UI adds a warning badge and a "Needs review" panel. It pairs naturally with Task A's approval inbox.
