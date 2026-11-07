# Agent Lifecycle Governance

## Purpose

This document defines how specialist roles in the MCP Factory agentic
ecosystem are created, evaluated, promoted, degraded, merged, split, and
retired over time.

Its primary goal is to make the ecosystem durable even when:

- the repo changes quickly
- the main thread context window is limited
- older role assumptions become stale
- new blocker families or product surfaces appear

The ecosystem must therefore use durable on-disk governance rather than
conversation memory as its source of role truth.

## Core Rule

Do not trust memory for role governance.

Use durable repo artifacts instead:

- role contracts
- evaluation artifacts
- implementation pack
- agent registry
- prompt construction notes
- skills
- `AGENTS.md`

The main thread should reload those artifacts when needed and treat them as the
operating memory of the ecosystem.

## What Every Recurring Role Must Have

Every recurring specialist role must have:

1. a role contract
2. at least one evaluation artifact
3. a registry entry
4. a current lifecycle state
5. a defined promotion condition
6. a defined degradation condition
7. a retirement or merge condition

No recurring role should become default workflow infrastructure until all of
those exist.

## Lifecycle States

Canonical lifecycle states:

- `candidate`
  - a role idea exists, but no real evaluation has happened yet
- `calibrating`
  - the role has at least one real evaluation and is still being refined
- `provisional`
  - the role is useful enough for supervised use, but should not be treated as
    stable infrastructure yet
- `stable`
  - the role has passed enough real evaluations that it may be used routinely
    under normal supervision
- `degraded`
  - the role was previously useful, but new repo evidence shows its output is
    drifting, noisy, or stale
- `merged`
  - the role has been folded into another role because the distinction was not
    real enough to keep
- `retired`
  - the role is no longer needed, no longer recurring, or is better handled by
    another role or by the parent thread

## Promotion Path

The normal lifecycle path is:

- `candidate`
- `calibrating`
- `provisional`
- `stable`

A role may also move:

- `calibrating -> merged`
- `calibrating -> retired`
- `stable -> degraded`
- `degraded -> provisional`
- `degraded -> retired`

## Promotion Conditions

Promote a role only when all of these are true:

- it has succeeded on multiple real tasks
- its output stays bounded
- its strongest failure modes are understood
- its citations are good enough for review
- the main thread repeatedly finds the role useful for next-branch choice
- the role no longer depends on prompt-by-prompt improvisation to stay useful

Suggested thresholds:

- `candidate -> calibrating`
  - first real evaluation artifact exists
- `calibrating -> provisional`
  - at least 2 real evaluations
  - role is directionally useful
  - major boundary confusion has been removed
- `provisional -> stable`
  - at least 3 successful real evaluations across separate tasks or checkpoints
  - no major overclaim in the last 2 evaluations
  - role can be safely dispatched without special caveats beyond its contract

## Degradation Conditions

Degrade a role when any of these are true:

- a previously useful role becomes noisy after repo changes
- its owned surfaces changed materially
- its outputs stop helping next-branch choice
- it begins overclaiming beyond its evidence
- another role or the parent thread must repeatedly repair its output

When degraded:

- do not remove the role immediately
- mark it `degraded`
- require a fresh evaluation before routine use continues

## Merge And Split Rules

### Split A Role When

- one role is doing two distinct jobs badly
- triggers are diverging
- output contracts are diverging
- evaluation criteria are no longer the same

### Merge A Role When

- two roles share the same trigger
- two roles share nearly the same output
- the distinction creates coordination cost without better results

Every merge or split decision must be recorded in:

- the affected role contracts
- the registry
- the next evaluation artifact touching that role

## Retirement Conditions

Retire a role when:

- the task is no longer recurring
- the role is no longer distinct
- another role absorbed it more cleanly
- the parent thread now handles it better than a specialist would
- repeated evaluations show the role is not worth the coordination cost

Retirement is not deletion of history.

Retired roles should remain documented in the registry so the system remembers:

- what the role was
- why it stopped being useful
- what replaced it, if anything

## Re-Evaluation Triggers

Re-evaluate a role when:

- files or artifacts in its owned surface changed materially
- a new blocker family appears that the role is expected to reason about
- the role’s outputs become noisy or contradictory
- a previously trusted output is later contradicted
- the role is about to be promoted to heavier workflow use
- the role is about to be mapped into an external tool or automation

For this repo, role re-evaluation should be strongly considered after:

- dashboard contract changes
- new run-ledger or compare-run semantics
- new verification doctrine in `AGENTS.md`
- new prompt-chain behavior for the ecosystem itself

## Continuous Evaluation Rule

Roles must be evaluated continuously, not once.

This repo is dynamic:

- the engine changes based on findings
- emitted artifacts change
- product surfaces change
- contracts evolve

Therefore, the ecosystem that operates on top of the repo must also remain
dynamic.

Every role should accumulate an evaluation history that answers:

- what it was tested on
- what it got right
- what it missed
- what it overclaimed
- what should change next

## Default Audit Suites

A default audit suite is a reusable workflow component, not a one-off prompt
trick.

When repo doctrine says a qualifying work class should use a default audit
suite, non-dispatch is acceptable only when:

- delegation authorization is absent
- the work is too small to benefit
- the required role does not exist
- the required role is too degraded for the current risk level
- the parent thread is intentionally holding the reasoning local to avoid a
  fragile split
- the triggering event did not happen

Any non-dispatch on qualifying work must be written back in the owning
artifact.

If a qualifying suite applies but a required role does not exist, the GM must
either:

- create or evaluate a bounded role candidate first
- or explicitly record why parent-thread-only handling is safer for this slice

## Context-Window Strategy

The parent thread must not try to remember the whole ecosystem from live
context alone.

Instead:

- strategic context stays in the parent thread
- role memory lives in contracts, evals, and the registry
- specialist threads receive only the local evidence slice they need

Parent thread keeps:

- wider goal
- current stop gate
- dominant blocker or role-gap
- currently trusted systems and roles

Parent thread reloads when needed:

- role contract
- recent eval
- registry state
- implementation pack

This is how the ecosystem survives context-window limits.

## Registry Requirements

The agent registry is the canonical state tracker for role lifecycle.

Each entry should include:

- `name`
- `family`
- `current_form`
  - `skill`
  - `custom_agent`
  - `prompt_only`
  - `parent_thread_only`
- `lifecycle_state`
- `owner_surfaces`
- `role_contract_path`
- `evaluation_artifact_paths`
- `recommended_model`
- `recommended_reasoning_effort`
- `recommended_sandbox_mode`
- `promotion_gate`
- `degradation_triggers`
- `re_evaluation_triggers`
- `merge_or_retirement_condition`
- `dispatch_trigger_mode`
- `mandatory_event_triggers`
- `blocking_mode`
- `skip_conditions`
- `notes`

Use those dispatch metadata fields only for roles whose triggers are
event-bound rather than purely advisory.

Canonical meanings:

- `dispatch_trigger_mode`
  - `advisory_fit`
  - `mandatory_event_bound`
- `mandatory_event_triggers`
  - the concrete event list that makes the role mandatory
- `blocking_mode`
  - whether the role is `non_blocking_default`, `blocking_after_event`, or
    `blocking_only_at_pause_or_handoff`
- `skip_conditions`
  - the honest bounded reasons the GM may record when a mandatory trigger fired
    but the role was still not dispatched

## Governance Rule For New Roles

Do not create a new recurring role just because it sounds useful.

Create a new recurring role only when all are true:

1. the task recurs
2. the trigger is stable
3. the output is distinct
4. the boundary is clear
5. evaluation would be possible on real repo work

## Governance Rule For External Tool Mapping

Only map a role into external tools or heavier automation when the role is at
least `provisional`.

Preferred order:

1. contract
2. real evaluation
3. refinement
4. provisional supervised use
5. external-tool or automation mapping

Do not export a noisy role into GitHub, CI, or other toolchains prematurely.

## Operating Conclusion

The ecosystem should improve the same way the engine improves:

- from findings
- through bounded evaluation
- under explicit contracts
- with durable artifacts

This governance layer exists so role refinement is continuous and reviewable,
not accidental and memory-dependent.
