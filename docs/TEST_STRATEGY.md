# Test Strategy

## Principles
- Follow the repository's existing test frameworks and conventions.
- Test observable behaviour rather than implementation details.
- Prefer focused tests for validation, permissions, edge cases, and failures.
- Do not claim coverage without running a coverage tool and recording the result.

## Baseline
Record the existing test commands and outcomes in `docs/ASSESSMENT.md` before implementation.

## Selected task
- Task:
- Critical user journey:
- Relevant backend modules:
- Relevant frontend modules:

## Test matrix

| Scenario | Layer | Expected result | Test added / existing test |
|---|---|---|---|
| Happy path | | | |
| Invalid input | | | |
| Unauthorised / wrong owner | | | |
| Empty or missing data | | | |
| Partial failure / external dependency failure | | | |
| Regression to existing behaviour | | | |

## Verification commands
List only commands confirmed to exist in this repository. Record exact commands and actual outcomes in `docs/REVIEW_REPORT.md`.

## Manual smoke test
Write a short, reproducible smoke-test sequence for the selected task. Do not claim it was completed unless it was actually performed.
