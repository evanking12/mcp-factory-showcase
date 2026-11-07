# Scoped Repo Cleanup Workflow Eval 01

## Role Tested

- `scoped-repo-cleanup`

## Current Form

- `skill`

## Prompt Used

- 04-scoped-repo-cleanup-docs-proof.md

## Task Input

- target ownership surface: `docs/`
- wider goal: make bounded cleanup reusable across ownership surfaces
- specialist roster:
  - `repo-hygiene-auditor`
  - `run-artifact-curator`
  - `code_review_bot`
  - `verification_gate_bot`

## Output Produced

- one scoped-cleanup orchestration skill
- one reusable prompt template
- one governance-inventory entry
- one bounded proof cycle on `docs/`
- one docs cleanup slice centered on
  [docs/architecture/README.md](../../README.md)

Boundary note:

- workflow implementation touched governance surfaces outside `docs/`
- the cleanup slice itself remained inside `docs/architecture/`

## What It Got Right

- used ownership-surface targeting instead of blind folder fanout
- reused existing specialist roles rather than inventing duplicate auditors
- stayed bounded to one primary docs cleanup slice
- made active versus historical architecture truth easier for humans and agents
- produced a reusable template that can now be applied to `api/`, `sessions/`,
  `ui/`, or repo-root clutter

## What It Missed

- it did not yet add a validation matrix by touched-surface type
- it did not yet create a dedicated machine-readable workflow status registry
  entry outside governance inventory

## What It Overclaimed

- the first doctrine wording for dispatch-by-default overreached until the
  review bot forced explicit precedence against the delegation-authorization
  rule

## Workflow Usefulness Judgment

- `good`

Why:

- the workflow reduced reinvention
- the specialist-role hierarchy remained coherent
- the resulting cleanup slice was safer and more reviewable than a generic
  cleanup pass

## Trust Decision

- `provisional`

Reason:

- one real ownership-surface proof now exists
- the workflow is reusable
- but it has only been proven on `docs/` so far

## Single Refinement Needed Next

- add one surface-aware validation matrix so cleanup cycles for `docs/`,
  `api/`, `sessions/`, and `ui/` do not each have to rediscover minimum checks

## Keep / Refine / Split / Merge / Retire

- decision: `refine`

## Recommended Next Proof Surface

- `sessions/`

Why:

- it is the next highest-noise surface
- it stresses transient-vs-durable distinctions
- it will test whether the workflow still stays bounded when file relocation is
  more tempting than clarification
