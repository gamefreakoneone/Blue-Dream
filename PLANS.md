# Execution Plan Template

Use this template before starting a feature that affects architecture, APIs, memory behavior, provider integration, capture, or UI workflow. Specs under `docs/specs/NNNN-feature-name/` already carry requirements/design/tasks; fill this template only when a piece of work is substantial and has no spec yet, or when a spec needs a mid-course re-plan.

## Title

Short feature name, matching the spec folder if one exists.

## Goal

State the user-visible outcome in one paragraph.

## Scope

- In scope:
- Out of scope:

## Current Context

List relevant files, prior decisions, spec documents, and constraints. Check `docs/FEATURE_STATUS.md` and `TECHNICAL_DESIGN.md` first.

## Design Decisions

- Chosen approach:
- Alternatives considered:
- Risks and mitigations:

## Interfaces

Document any public contract changes:

- API routes
- Data shapes (MongoDB collections, Pydantic models)
- Environment variables
- Provider/model configuration

## Tasks

1. Documentation updates
2. Implementation steps
3. Tests and validation
4. Manual demo checks

## Acceptance Criteria

- What must work:
- What must not regress (see the "contracts you must not break" box in the relevant spec design):
- What evidence proves it:

## Verification

List commands, browser checks, and manual scenarios to run. Record evidence in the spec's `status.md` and update `docs/FEATURE_STATUS.md` in the same change.
