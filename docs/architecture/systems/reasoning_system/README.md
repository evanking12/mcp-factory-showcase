# Reasoning System

## Purpose

The reasoning system owns stage intelligence and semantic judgment.

Its job is to transform raw execution output into:

- reusable evidence
- bounded diagnoses
- semantic checkpoint conclusions
- next-step recommendations

If the execution system answers whether something ran, the reasoning system
answers what that run means.

## Owned Surfaces

Primary owned code areas:

- `api/pipeline/`
- `api/analysis/`

Important sub-areas:

- stage orchestration
- evidence candidate selection
- prereq inference
- probe-loop behavior
- gap resolution
- semantic checkpoint comparison
- direct-target truth shaping
- diagnosis/blocker shaping

## Primary Inputs

- discovery outputs
- executor results
- checkpoint state
- prior evidence and same-run lineage
- authored suite manifests and expected semantic contracts

## Primary Outputs

- promoted findings
- semantic checkpoint outcomes
- compare reports
- ranked evidence and diagnoses
- blocker-family conclusions
- next-step and proof posture summaries

## Public Contracts

Critical contracts include:

- handoff contract and stage registry
- finding status taxonomy
- compatibility policy
- canonical evidence ranking and classification semantics
- compiled-ingest compare-report surfaces

Reasoning changes must preserve backward-tolerant readers where strict schemas
already exist.

## Invariants

- runtime evidence outranks static discovery
- static discovery outranks model inference
- stateful success must not be promoted like confirmed truth when replay or
  downstream evidence contradicts it
- the system must start generic and specialize through evidence
- suite-specific lessons must not become hardcoded generic-engine behavior

## Common Failure Modes

- overpromoting provisional success
- brittle wrapper or replay semantics hiding the real state story
- wrong prereq binding causing false local failures
- semantic checkpoint success claimed without enough reusable evidence
- lifecycle consumers using stale or foreign lineage
- blocker-family drift where downstream consequences outrank root causes

## Observability Gaps

Current recurring gaps include:

- state/lineage coverage is still under-surfaced to operators
- capability-family progress is not yet a first-class UI surface
- hard-band ambiguity systems are documented but not yet proven in live
  operator-facing form

## Typical Tests And Checks

When this system changes, likely checks include:

- focused pipeline-stage tests
- compiled-ingest suite tests
- direct-target truth tests
- gap-resolution and probe-loop tests
- `python scripts/verify_sync.py --tier A`
- full harness suite when the touched area is broad

If classification taxonomy changes:

- run `python scripts/verify_sync.py --tier B`

## Agent Guidance

Use this doc before editing when the task involves:

- semantic mismatch
- incorrect blocker-family promotion
- stage reasoning
- wrong lineage reuse
- probe behavior
- compare-report interpretation

Do not fix reasoning around missing or unstable execution evidence if the real
problem is still execution-system instability.

## Do Not Own

The reasoning system does not own:

- port wiring
- subprocess lifecycle
- health endpoints
- UI layout and operator interaction model
- canonical execution law for agents
