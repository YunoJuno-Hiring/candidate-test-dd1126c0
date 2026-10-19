# Repository Assessment

> Stage 00 document. Everything below was observed in the repository or produced by a command that was actually run on 2026-10-17. Inferences are labelled as such.

## 1. Repository snapshot

- **Current branch:** `main`, up to date with `origin/main`. HEAD `446e97e README updates`.
- **Initial `git status`:**
  - Staged (new): `.claude/commands/00..05-*.md`, `CANDIDATE_NOTES_TEMPLATE.md`, `CLAUDE.md`, `WORKFLOW.md`, `docs/*.md`, `docs/diagrams/README.md`.
  - Modified (unstaged): the same workflow files, plus **`README.md`**.
  - Untracked: `.idea/`, `docs/diagrams/*.mmd` (generic templates, replaced in this stage).
  - **Important:** the working-copy `README.md` has been overwritten with the Claude Code workflow README. The assignment brief only exists in `HEAD:README.md` (read with `git show HEAD:README.md`). This must be restored before submission or it will appear in the PR diff. Not changed in this stage.
- **Runtime/tool versions observed on the host:**
  - `python3` 3.15.0; `python3.11` exists at `/opt/homebrew/bin/python3.11` but has no Django installed.
  - `node` v24.21.0, `corepack` 0.36.0.
  - `docker` 29.5.3, `docker compose` v5.1.4.
  - **Not installed:** `uv`, `pnpm`, `task`. So `task test` / `task seed` cannot run directly on the host.
  - Containers running: `candidate-test-dd1126c0-db-1` (postgres:18) and `candidate-test-dd1126c0-mailpit-1` (healthy). Postgres reachable on `localhost:5432`.
  - `frontend/node_modules` is already populated (react, react-query, router, vite, typescript, tailwind). `frontend/dist` exists (gitignored).
- **Backend structure** (`backend/`, Django 5.1 + DRF 3.15, `pyproject.toml` + `uv.lock`):
  - `config/` – settings (Postgres via `python-decouple`, DRF `TokenAuthentication` + `IsAuthenticated` defaults, SMTP email to `localhost:1025` = Mailpit), root URLs.
  - `accounts/` – `Company(name, billing_email)`, `CompanyAdmin(user 1:1, company FK)`, `Freelancer(user 1:1, name)`; login view, freelancer list.
  - `contracts/` – `Contract`, `TimesheetEntry`; list/detail/create views (plain `APIView`, inline permission checks).
  - `billing/` – empty `models.py` (comment only), stub views, no migrations.
  - `webhooks/` – empty `models.py` (comment only), stub views, no migrations.
  - `core/management/commands/seed.py` – idempotent seed (`get_or_create` / `update_or_create`).
  - `conftest.py` – shared pytest fixtures (`api_client`, `admin_client`, `freelancer_client`, `northstar`, `meridian`, `active_contract`, `other_contract`, `submitted_entry`).
- **Frontend structure** (`frontend/`, React 18 + TS strict + Vite 6 + Tailwind 3 + TanStack Query 5 + React Router 6):
  - `src/api/client.ts` – `fetch` wrapper, `ApiError`, shared types. One module per domain in `src/api/`.
  - `src/pages/` – `Login`, `ContractList`, `ContractDetail`, `NewContract`, `SubmitHours`, `Billing`, `InvoiceDetail`, `DeveloperSettings`.
  - `src/components/` – only `Nav` and `StatusBadge`. No shared Button/Table/Modal primitives; pages use inline Tailwind classes.
  - `src/hooks/useAuth.tsx` – token + user in `localStorage`, `isAdmin` / `isFreelancer`.
  - Vite dev server proxies `/api` to `localhost:8000`.
- **Database and local services:** `docker-compose.yml` defines only `db` (postgres:18) and `mailpit`. **There is no `webhook-receiver` service in docker-compose**, even though the README says it runs there. `services/webhook-receiver/` (Express, in-memory log, `POST /hook`, HTML UI on `/`) has a Dockerfile and a `task receiver` entry that runs it with local `node`.
- **Relevant API routes** (all under `/api/`):

  | Route | Methods | State |
  |---|---|---|
  | `auth/login/` | POST | Real |
  | `freelancers/` | GET (admin only) | Real |
  | `contracts/`, `contracts/<id>/` | GET, POST (admin) / GET | Real |
  | `timesheets/` | GET (`?status`, `?contract`), POST (freelancer) | Real |
  | `timesheets/<id>/` | PATCH | Real, but weak validation (see §3) |
  | `billing/runs/` | POST | Stub: `{'run_id': 'stub', 'invoices_generated': 0, ...}` |
  | `invoices/`, `invoices/<id>/` | GET | Stub: `[]` and 404 |
  | `webhook-endpoints/`, `webhook-endpoints/<str:pk>/` | GET, POST / DELETE | Stub: `[]`, echo, 204 |

- **Models and migrations:** `accounts/migrations/0001_initial.py`, `contracts/migrations/0001_initial.py`. `billing/migrations/` and `webhooks/migrations/` contain only `__init__.py`. `TimesheetEntry` has `unique_together = (contract, date)`, `hours` Decimal(5,2), `status` choices draft/submitted/approved/rejected, nullable `rejection_reason`. `Contract.daily_rate` Decimal(8,2).
- **Test locations and conventions:** pytest + pytest-django; function-style tests with `@pytest.mark.django_db`; files `<app>/tests/test_*.py`; DRF `APIClient` with token credentials from `conftest.py`. Tests exist for `accounts` and `contracts` only. **No frontend test runner** is installed or configured (no vitest/jest/testing-library in `package.json`). **No linter or formatter** is configured for either side (no ruff/flake8/eslint/prettier config).

## 2. Baseline checks

| Check | Command actually run | Result | Notes / existing failures |
|---|---|---|---|
| Backend tests | `docker run --rm -v backend:/app:ro ... ghcr.io/astral-sh/uv:python3.11-bookworm-slim uv run --frozen pytest -p no:cacheprovider -q` (with `DB_HOST=host.docker.internal`) | **41 passed** in 22.98s | Host lacks `uv`, so ran in a throwaway container with the repo mounted read-only. Dependencies came from `uv.lock` (`--frozen`), into the container only. Nothing was installed in the repo or on the host. |
| Django system check | same container: `uv run --frozen python manage.py check` | **No issues** | |
| Migration drift | same container: `uv run --frozen python manage.py makemigrations --check --dry-run` | **No changes detected** (exit 0) | |
| Frontend type check | `frontend/node_modules/.bin/tsc --noEmit` | **Passed** (exit 0) | `pnpm` not installed; used the local binaries in `node_modules/.bin`. |
| Frontend build | `node_modules/.bin/tsc && node_modules/.bin/vite build` | **Passed** (95 modules, JS 235.29 kB) | Rewrote the gitignored `frontend/dist`. |
| Frontend tests | — | **Not run: no test runner exists** | |
| Lint | — | **Not run: no linter configured** | |
| Behaviour probe (throwaway) | 3 ad-hoc pytest cases in a container copy of `backend/` (file kept in the session scratchpad, not in the repo) | See §3 findings 1–3 | Repo not modified. |

## 3. Existing behaviour relevant to the exercise

**Complete:** login; contract list/detail/create scoped by company or freelancer; timesheet list scoped by role with `?status` and `?contract` filters; freelancer submit (always saved as `submitted`); admin approve/reject via PATCH with a required reason on reject. Company isolation on reads is covered by tests.

**Rough edges, confirmed by the throwaway probe (`TimesheetDetailView.patch`, `backend/contracts/views.py:133-165`, serializer `backend/contracts/serializers.py:35-42`):**

1. **A freelancer can approve their own entry.** `PATCH {"status": "approved"}` as the freelancer returned `200` with `status=approved`. There is no role check on status changes.
2. **An admin can move an entry to another company's contract.** `PATCH {"contract": <meridian contract id>}` as the NorthStar admin returned `200`, and the row's `contract_id` changed. The serializer's `contract` field is writable against `Contract.objects.all()`.
3. **No state machine.** An `approved` entry was changed to `draft` with `hours=20` (`200`). Any field (`hours`, `date`, `contract`) is editable at any status.

**Other observations:**

- The timesheet list returns only `contract` (an id). No freelancer name, contract rate, or company. There are no `freelancer` or date-range filters and no pagination.
- **Cost convention is ambiguous.** `Contract.daily_rate` is a **daily** rate. The README says "hours × contract rate". `ContractDetail.tsx:45` estimates cost as `hours × daily_rate / 8`. Seed hours are 7.5 or 8.0 per day.
- Seed (`seed.py`) creates NorthStar and Meridian, six contracts (two closed), and entries from Jan 1 to yesterday: older months mostly approved, last month mixed (draft/submitted/approved), current month draft/submitted. Billing emails are `billing@northstar.example.com` and `accounts@meridiandigital.example.com`.
- `Billing.tsx` POSTs `{month: "YYYY-MM"}`, shows `invoices_generated`, refetches the list. The invoice list renders only `id`. `InvoiceDetail.tsx` renders the raw JSON and has a 404 state. The `Invoice` type is `{id, [key]: unknown}`, so the backend can choose the shape.
- `DeveloperSettings.tsx` supports create (URL only) and delete only. There is no edit, no "send test event", and no delivery log UI. The webhook detail route uses `<str:pk>`, which accepts the stub's `'stub'` id.
- Billing and webhook stubs only require `IsAuthenticated`, so a freelancer can call them. The `/billing` and `/developers` nav links are hidden for non-admins in the UI only.
- Known TODOs in the code: permission mixin extraction (`contracts/views.py:55`), django-filter (`:103`), moving the rejection check into the serializer (`serializers.py:36`), and the redundant `contract_id` field.

## 4. Task options

### Task A — Frontend Approval Inbox
- **Existing backend support confirmed:** `GET /api/timesheets/?status=submitted` (company-scoped) and `PATCH /api/timesheets/<id>/` with approve or reject-with-reason. `GET /api/contracts/` provides freelancer names and rates for a client-side join.
- **Frontend work likely needed:** a new admin-only route and nav link; a page that joins entries with contracts; filters (contract, freelancer, date range — client-side, or new query params); row selection and select-all; bulk approve; a bulk reject modal with a required reason; a running cost total; empty, loading, error, and partial-failure states. Bulk can be N parallel PATCH calls (`Promise.allSettled`) or a new bulk endpoint, which is a design decision.
- **Key risks and edge cases:** partial failures in bulk; stale rows (an entry already actioned elsewhere); optimistic-update rollback; cost formula ambiguity (`/8`); probe findings 1–3 mean "backend is ready" is not fully true (self-approval, transitions), and fixing them is arguably out of scope; no frontend primitives to reuse, so components must be created.
- **Likely tests:** frontend component and hook tests (selection, total, reject validation, partial failure). **This needs new dev dependencies** (vitest, @testing-library/react, jsdom, likely msw), which needs your approval. Backend tests would be needed if filters or a bulk endpoint are added.
- **Scope/time assessment:** medium. UI polish can expand without limit. Extra cost: test infrastructure setup. Evaluation focuses on UX and state judgement.

### Task B — Backend Monthly Billing Run
- **Existing billing models/endpoints confirmed:** three stub endpoints with routes wired; no models and no migrations; the UI is wired (`Billing.tsx`, `InvoiceDetail.tsx`, `api/billing.ts`). `billing/models.py` states the intended grain: one invoice per Company × Freelancer × month, idempotent, delivered by email.
- **Data model and transaction implications:** likely `Invoice` (company, freelancer, contract?, period month, totals, status, sent timestamp) and `InvoiceLine` linked to `TimesheetEntry` (or a nullable FK on the entry), with a unique constraint on (company, freelancer, month) for idempotency. Must decide whether to bill per contract or per company+freelancer (a freelancer can have more than one contract at the same company). Must also decide what happens to entries approved after a run (top-up invoice or ignore) and whether invoiced entries are locked. Run inside `transaction.atomic()` with `select_for_update` or the unique constraint to survive concurrent runs. Calculate money with `Decimal`, not float.
- **Email and failure-handling implications:** do not send email inside the DB transaction. Commit the invoice, then send through `transaction.on_commit` or a separate send step. Record `email_status` / `sent_at` so a failed send can be retried by re-running the job without duplicate invoices. Two recipients: company `billing_email` and the freelancer's `user.email`. `settings.EMAIL_BACKEND` is SMTP to Mailpit; tests can use Django's locmem backend (`mailoutbox` fixture from pytest-django).
- **Permissions:** company admins only, scoped to their own company (the current stubs allow any authenticated user). Freelancers possibly read-only on their own invoices (decision needed).
- **Likely tests:** pytest API tests for the run (creates the right invoices, only approved entries in the month, month boundaries, ignores other companies), idempotency (second run creates 0), email sent to both recipients, email failure leaves the invoice committed and marked unsent and retryable, list/detail scoping and 404s, input validation (`month` format), and 403 for freelancers. All of this fits the existing conftest patterns.
- **Scope/time assessment:** medium. Self-contained in `billing/`. Small UI change optional (the list currently shows only `id`). No new dependencies. Highest testability with the existing infrastructure.

### Task C — Fullstack Outbound Webhooks
- **Existing integration/settings code confirmed:** stub list/create/delete endpoints; an empty `webhooks/models.py`; `DeveloperSettings.tsx` with create and delete only; `services/webhook-receiver` (not in docker-compose; run with `task receiver` or its Dockerfile).
- **Endpoint model and API work likely needed:** `WebhookEndpoint` (company, URL, secret, active, created), `WebhookDelivery` (endpoint, event id, event type, payload, attempt, response code, error, timestamps). CRUD plus a test-event action plus a delivery list. Frontend: edit, toggle active, delete confirmation, test button, delivery log table, and secret display once. These are new API functions and types.
- **Event delivery and failure-handling implications:** no queue exists. Options: synchronous on `on_commit` with a timeout (simple, but blocks the request and has no retries); a DB-backed outbox plus a management-command worker; or adding Celery/RQ plus Redis (new services and dependencies). Retry/backoff, giving up, and long outages all need either code or written reasoning. An outbound HTTP client is needed (`urllib` from the standard library, or adding `requests`/`httpx`).
- **Security considerations:** HMAC-SHA256 signature with a timestamp; secret storage and one-time display; SSRF risk (the user supplies URLs, so restrict schemes and private IPs in production); company scoping on all endpoints.
- **Likely tests:** backend model and API tests, signing, the delivery log, retry logic with a mocked HTTP layer, and event emission on the chosen transition. Frontend tests need the same new test tooling as Task A.
- **Scope/time assessment:** large. It spans both layers, has the most design decisions, and has the highest risk of exceeding the 2–3 hour guidance. The receiver is also missing from docker-compose, which adds setup friction.

## 5. Recommendation

**Recommend Task B (Backend Monthly Billing Run).**

Evidence:
- The UI and routes are already wired, so the work is concentrated in one Django app (`billing/`) with a clear, testable contract.
- The pytest + pytest-django + conftest fixture infrastructure works today (41 passing), so meaningful tests (idempotency, transaction and email failure, scoping) can be written in the house style with **no new dependencies**.
- The brief's evaluation criteria for B (data modelling, idempotency, transaction boundaries, testing) can be shown in depth inside the time guidance.
- It fits later work: invoice lines linked to timesheet entries give Task C a natural `invoice.created` event and give Task A a reason to lock billed entries.

Trade-offs:
- B shows less frontend skill. A small, optional improvement to the invoice list/detail display could address this, but only if you approve it.
- A is the most visible to users but needs new frontend test dependencies, and its correctness relies on a PATCH endpoint with confirmed authorisation and state-transition gaps.
- C shows the most breadth but has the highest scope and the highest risk of overrunning.

## 6. Questions / unknowns

These materially affect implementation:

1. **Cost/amount formula.** Should the amount be `hours / 8 × daily_rate` (matches `ContractDetail.tsx:45`), or something else? This affects A (running total) and B (invoice totals).
2. **README.md working copy.** Restore the assignment README before submission? (Recommended: yes, in Stage 05, with your approval.)
3. **For B:** should each invoice be per contract or per company × freelancer (the `billing/models.py` comment says company × freelancer)? What should happen to entries approved after a month was billed?
4. **For A or C:** can I add frontend dev dependencies (vitest + Testing Library + jsdom)?
5. **Backend PATCH gaps (findings 1–3).** Leave and document, or fix as a blocker? They block A's integrity more than B's. For B, invoiced entries could still be edited later.
6. **Not verified:** the app running end to end in a browser (backend dev server and seed not run in this stage); the webhook receiver running.

## 7. Decision gate

**STOP:** Choose exactly one task (A, B, or C). No application code has been edited.
