# AI-Assisted Timesheet Anomaly Detection — Idea Proposal

> Exploration only. Nothing here is implemented. Written 2026-10-19 after Task C was completed, to review ideas before any build decision.

## Goal
Help a company admin review submitted timesheets faster and more safely by flagging entries that look unusual, and explaining *why* in plain language. Example: a freelancer who normally logs about 7.5 hours a day submits 14 hours for one day.

The system **flags and explains**; it never approves or rejects on its own. The admin decides.

## The three approaches I would combine

### 1. Historical average — statistics
A freelancer has averaged 7.5 hours a day over the last 30 days. If they enter 14 hours today, the system flags it.

The check measures how far the new value is from the recent average, using the standard deviation (a z-score) of the last 30 days. If there is not enough history (for example, fewer than 10 working days), the system says so instead of guessing.

The first choice here is statistical analysis, not AI: it is cheap, deterministic, explainable and easy to test.

### 2. Spending anomaly — cost analysis
A company's contract normally costs about £4,000 a month, but one month it rises to £7,000. The system finds which freelancers and how many extra hours caused the increase.

The calculation is done in ordinary code. AI can then summarise and explain the result.

### 3. AI explanation — LLM
When the system flags the 14-hour entry, an LLM can produce an explanation such as:

> "This entry is significantly higher than the freelancer's recent average of 7.5 hours. Please review it before approval."

The LLM's job is not to calculate anything. Its job is to explain the findings, which were already computed from the data, in a way the admin can understand.

## Which technique fits which check

| Check | Rule-based | Statistical | LLM adds value? |
|---|---|---|---|
| Hours above a hard limit (e.g. > 12 h/day, > 24 h across all contracts on one day) | **Yes** — fixed thresholds | — | No |
| Entry outside the contract dates, on a closed contract, or on a weekend when the freelancer never works weekends | **Yes** | Weekend habit is statistical | No |
| Day far above the freelancer's own daily average | — | **Yes** — z-score vs last 30 days | Only to explain |
| Week far above weekly average, or a sudden change in pattern (e.g. 5 × 7.5 h becoming 5 × 11 h) | — | **Yes** — rolling weekly totals, change vs previous 4 weeks | Only to explain |
| Possible duplicates | **Yes** — same freelancer, same date, different contracts; or an identical block of hours copied from the previous week | — | No |
| Monthly cost spike for a contract or freelancer | Cost formula is code | **Yes** — month vs trailing 3–6 month average, then break down the delta by freelancer and hours | **Yes** — summarise the breakdown |
| Admin-facing summary ("3 entries need attention this week, mainly Alex's Friday") | — | — | **Yes** — this is where an LLM genuinely helps |
| Reading free text (future: entry descriptions, rejection reasons) | — | — | **Yes** — classify or summarise text |

**Conclusion:** detection is rules + statistics. The LLM is used for **explanation and summarisation** of findings that code has already produced. This keeps the numbers correct and auditable, keeps cost low, and means the feature still works (with template text) if the LLM is unavailable.

## Data needed
Already in the repository:
- `TimesheetEntry`: `contract`, `date`, `hours`, `status`, `rejection_reason`. `unique_together = (contract, date)` already prevents exact duplicates on one contract, so duplicate detection should look **across contracts** for the same freelancer, and at copied patterns.
- `Contract`: `company`, `freelancer`, `daily_rate`, `start_date`, `end_date`, `status`.
- `Freelancer`, `Company`.

Gaps and decisions:
- **Cost formula is ambiguous** (assessment finding 3): `daily_rate` is daily; the UI estimates `hours × daily_rate / 8`. The anomaly feature must use one agreed formula.
- **History depth:** the seed has roughly 40 entries from January onwards. Enough to demonstrate, not enough to tune thresholds. Minimum-history rules are essential.
- **Useful later:** entry descriptions (what was worked on), approval timestamps (for approval-SLA tracking), public holidays per country.

## Simple technical approach (Django + React)

### Backend
- New app `anomalies/` (same layout as `webhooks/`).
- `anomalies/checks.py`: pure functions, one per check, each returning a `Finding` (check name, severity, the numbers it used, e.g. `{"hours": 14, "avg_30d": 7.5, "std_30d": 0.4, "z": 16.2, "history_days": 21}`). Easy to unit-test with the existing pytest fixtures.
- Model `TimesheetFlag`: entry FK, check name, severity, `evidence` JSON, `explanation` text, `explanation_source` (`template` or `llm`), created timestamp, `reviewed_by` / `reviewed_at`.
- **When checks run:** on submit, in the same place `timesheet.submitted` is emitted today (`contracts/views.py`). The checks are fast database queries, so they can run in the request; the LLM explanation should not. Store the flag with a **template explanation** immediately, then fill in the LLM explanation asynchronously. The outbox + worker pattern from Task C can be reused for this, so the submit request never waits for the LLM.
- Monthly cost checks run as a management command (e.g. `manage.py detect_cost_anomalies --month 2026-10`), reusing the same worker style.
- API: `GET /api/timesheets/?flagged=true` (or a `flags` field on each entry) and `GET /api/anomalies/cost/?month=YYYY-MM`. Company-scoped like every other admin endpoint.
- Optional: a `timesheet.flagged` webhook event, using the Task C delivery system.

### LLM explanation
- **Input:** only the structured findings and minimal context (ids, numbers, dates). No personal data beyond what the explanation needs; no free-form database dumps.
- **Output:** structured JSON (`summary`, `reasons[]`, `suggested_action`), validated against a schema (Claude API structured outputs: `output_config.format`, or `client.messages.parse()` in the Python SDK).
- **Guardrails:** the prompt states the LLM must not invent numbers; the code checks that any number in the explanation appears in the evidence, otherwise falls back to the template text. The LLM never changes a status.
- **Model:** default `claude-opus-5-5`. Explanations are short and frequent, so a cheaper model (e.g. Claude Haiku 4.5 or Claude Sonnet 5.5) is worth measuring against a small eval of real flags — that is a cost decision to make with data, not up front.
- **Cost:** keep the system prompt and instructions identical across calls so prompt caching applies; batch the monthly cost summaries (Message Batches API, about 50% cheaper, results within hours).
- **Fallback:** if the API fails or times out, the template explanation stays. The feature degrades, it does not break.

### Frontend
- Contract detail and (future) approval inbox: a warning badge on flagged entries, with the explanation in a tooltip or expandable row.
- A small "Needs review" panel on the admin dashboard listing this week's flags, with the LLM summary at the top.
- Loading, empty and error states as in the existing pages; vitest tests for the badge and panel.

## Suggested order
1. Rule-based checks (hard limits, cross-contract duplicates, outside contract dates). Highest value per hour of work, no AI.
2. Statistical checks (daily z-score, weekly pattern change) with minimum-history handling.
3. Template explanations and the UI badge. The feature is useful at this point without any LLM.
4. LLM explanation and weekly admin summary, asynchronous, with fallback.
5. Monthly cost-spike analysis with breakdown and LLM summary.

## Risks and open questions
- **False positives** annoy admins and get ignored. Start with conservative thresholds and let admins dismiss flags; measure the dismiss rate.
- **Fairness:** a flag must never be treated as an accusation. The wording should say "unusual compared with recent history", not "suspicious".
- **Privacy:** sending timesheet data to an external LLM needs a clear data-processing basis; send aggregates and ids, not names, where possible.
- **Small history:** new freelancers have no baseline. Fall back to contract-level or company-level norms, and say so.
- **Interaction with Task A (approval inbox):** flags are most useful exactly where admins approve in bulk. The two features fit together.
