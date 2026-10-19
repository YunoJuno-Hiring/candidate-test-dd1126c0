# YunoJuno Candidate Exercise — Working Rules

## Goal
Complete exactly ONE task from the supplied YunoJuno take-home README, prioritising correctness, clear reasoning, maintainability, and appropriate tests over breadth.

## Repository context
The repository is a Django REST Framework backend and React 18 + TypeScript + Vite frontend. Follow the existing architecture, conventions, libraries, and test patterns. The README is the source of truth for the assignment.

## Mandatory workflow
Follow `WORKFLOW.md` in order. Use the slash commands in `.claude/commands/` when supported by this Claude Code setup; otherwise follow the corresponding Markdown file as instructions.

### Approval gates
1. Stage 00: inspect the repository, run baseline checks where practical, document findings, create diagrams, compare tasks A/B/C, and STOP to ask me which task to select. Do not modify application code.
2. Stage 01: prepare acceptance criteria, implementation plan, and test plan. STOP for approval before implementation.
3. Stage 02: implement incrementally, with tests. Do not expand scope without asking.
4. Stage 03: run relevant tests and quality checks; distinguish pre-existing failures from regressions.
5. Stage 04: perform an independent review and document findings. STOP for approval before applying substantial review fixes.
6. Stage 05: verify the final diff and prepare `CANDIDATE_NOTES.md`. Do not commit, push, or open a PR unless I explicitly authorise it.

## Engineering rules
- Inspect before changing. Do not assume a file, endpoint, test command, or behaviour exists; verify it.
- Do not replace project conventions with a new architecture without a clear need.
- Keep changes focused on the selected task.
- Write or update tests for meaningful behaviour and edge cases.
- Never claim a command passed unless it was actually run and its result observed.
- Never hide failures. Report commands that could not be run and why.
- Do not remove unrelated user changes or reset the repository.
- Do not add dependencies unless needed; explain and ask first when the impact is material.
- Do not commit, push, or submit anything without explicit approval.
- Never put secrets, credentials, or real personal data in source files or candidate notes.

## Assignment-specific reminders
- The README offers three alternatives: A) Frontend Approval Inbox, B) Backend Monthly Billing Run, C) Fullstack Outbound Webhooks. Choose ONE only after repository assessment.
- The exercise says rough edges outside the chosen task should generally be left alone unless they block the task.
- The root `CANDIDATE_NOTES.md` is part of the submission. Explain what was built and why, key implementation choices, testing and AI-assisted workflow, and what would be done with four more hours. Be factual and concise.
