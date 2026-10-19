# Take-home Workflow

Work in the repository root. Keep all project-specific documents in English.

## Stage 00 — Assess and Diagram
Read the README end-to-end and inspect the actual repository before proposing implementation.
- Inspect Git status and preserve pre-existing changes.
- Inspect `Taskfile`, Docker Compose, backend and frontend structure, API routes, models, migrations, UI patterns, and tests.
- Identify documented commands and run safe baseline checks where practical.
- Record what was observed versus what remains unknown.
- Compare tasks A, B, and C using scope, risks, existing code, testability, and likely time.
- Create the diagrams listed in `docs/diagrams/README.md`.
- Write `docs/ASSESSMENT.md`.
- Do not modify application code.
- STOP and ask me to choose exactly one task.

## Stage 01 — Plan
After I select a task:
- Trace the relevant existing flow through UI, API, data model, and tests.
- Write acceptance criteria and explicit out-of-scope items.
- Identify likely files to change, data/API implications, failure modes, and tests.
- Update `docs/IMPLEMENTATION_PLAN.md` and `docs/TEST_STRATEGY.md`.
- STOP and ask for approval before implementation.

## Stage 02 — Implement Incrementally
After approval:
- Work in small, reviewable slices.
- Follow established code patterns.
- Add tests alongside meaningful behaviour.
- Run targeted checks after each logical slice.
- Keep the diff focused; do not silently add optional features.
- If a significant design decision or scope change emerges, explain the trade-off and ask.

## Stage 03 — Verify
- Run the most relevant backend and frontend tests.
- Run lint, type checks, build, integration, or smoke tests only where supported by the repository.
- Review edge cases and failure paths for the selected task.
- Record exact commands and outcomes in `docs/REVIEW_REPORT.md`.
- Distinguish baseline failures from failures introduced by the changes.
- Do not claim coverage improved unless coverage was measured.

## Stage 04 — Review
Review the diff as if you were a separate reviewer:
- correctness and requirements coverage
- security, permissions, and data ownership
- transaction and failure handling where relevant
- frontend loading, empty, success, and error states where relevant
- API compatibility and validation
- tests and maintainability
- accidental unrelated changes
Write findings, severity, and evidence in `docs/REVIEW_REPORT.md`.
STOP and show me material findings before making substantial review-driven changes.

## Stage 05 — Finalise
- Check each acceptance criterion against implementation and tests.
- Run final relevant checks and `git diff --check`.
- Inspect `git status` and the final diff.
- Create root `CANDIDATE_NOTES.md` from `CANDIDATE_NOTES_TEMPLATE.md`.
- Give me a concise summary, test results, known limitations, and a suggested PR title/body.
- Do not commit, push, or create/open a PR unless I explicitly authorise it.
