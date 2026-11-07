# Operator System

## Purpose

The operator system owns the human-facing product surfaces.

Its job is to convert backend truth into a usable operator decision surface.

If the reasoning system knows what is happening, the operator system must make
that understandable to a human without requiring raw artifact inspection.

## Owned Surfaces

Primary owned code areas:

- `dashboard/`
- `ui/`

Related surfaces:

- dashboard proxy and lab controls
- operator-facing status and coverage surfaces
- restart affordances that are exposed to humans

## Primary Inputs

- diagnoses
- ranked evidence
- compare-run and compiled-ingest summaries
- lab status
- chain-step and pipeline-stage context
- proof posture and residual blocker information

## Primary Outputs

- cockpit views
- run selectors
- current-context panels
- evidence cards
- product-facing capability summaries
- human-readable chain and stage narratives

## Public Contracts

Critical contracts include:

- dashboard route contracts
- UI route and API expectations
- operator layout and density expectations
- chain-step vs pipeline-stage distinction
- coverage and proof posture language

## Invariants

- the dashboard and the agent should tell the same practical story
- the operator must not be forced to infer the main blocker from raw logs
- chain step and pipeline stage must remain separate concepts
- major UI surfaces should rank by decision value, not by easy implementation
- operator language should be product-readable, not just engineer-readable

## Common Failure Modes

- green health with misleading decision surfaces
- evidence exists but the UI still reads as generic gray text
- root cause buried under downstream consequence
- capability progress invisible even when suite progress improved
- human-readable labels not aligned with authored chain semantics

## Observability Gaps

Current high-priority missing surfaces:

- per-case function-flow coverage
- blocker-family coverage
- state-initialization and lineage-materialization coverage
- product-facing capability framing:
  - surface coverage
  - workflow coherence
  - lineage reuse
  - branch truth
  - freshness / stale-state control

## Typical Tests And Checks

When this system changes, likely checks include:

- dashboard cockpit tests
- UI route or lab surface tests
- `python scripts/verify_sync.py --tier A`
- lane recycle and health checks if proxy/lab/control surfaces changed

## Agent Guidance

Use this doc before editing when the task involves:

- dashboard usability
- operator wording
- evidence presentation
- current-context or chain/stage surfaces
- product-facing coverage views

Default related skill:

- `ui-sync-auditor`

## Do Not Own

The operator system does not own:

- semantic truth itself
- artifact persistence
- worker lifecycle
- governance law

It owns presentation and operator usability of those truths.
