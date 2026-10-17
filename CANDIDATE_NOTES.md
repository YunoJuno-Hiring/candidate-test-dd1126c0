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

I left these unchanged during the assessment. Each one is either fixed or explicitly deferred later, depending on the task I select.

## What I built and why
To be completed after task selection and implementation (Stage 05).

## Implementation notes
To be completed after task selection and implementation (Stage 05).

## Testing and verification
To be completed after task selection and implementation (Stage 05).

## Workflow and AI assistance
To be completed after task selection and implementation (Stage 05).

## What I would do with four more hours
To be completed after task selection and implementation (Stage 05).
