# Family Blocker And System Writeback

## Purpose

This document defines how Codex must document recurring bug families,
proving-unlock blockers, and proposed next-system additions during autonomous
or semi-autonomous work.

This exists so family blockers do not remain:

- vague verbal patterns
- scattered commit commentary
- transient campaign notes
- or implied knowledge in prompt history

Use this contract when repeated findings suggest the issue is larger than one
local bug and smaller than a full product redesign.

## When To Write One

Write or update a family-blocker/system entry when any of these are true:

- the same bug shape appears in more than one bounded fix cycle
- different files exhibit the same underlying boundary failure
- a proving suite repeatedly stalls at the same seam
- repeated review findings point to the same missing reusable control
- `hard-01` or `hard-02` progress is being limited by a system gap rather than
  a single defect
- a cleanup or hygiene campaign reveals a deeper recurring architecture flaw

Do not create one for:

- one-off local defects with no repeating pattern
- purely cosmetic cleanup
- speculative future systems with no current evidence pressure

Campaign closeout is the required decision point for this classification. If a
campaign finds a meaningful blocker, rerank, or reusable system lesson, the
closeout must state whether it is `local_bug`, `family_blocker`, or
`missing_system` and record where the writeback was made or why it was deferred.

## Required Classification

Every candidate must be classified as exactly one of:

- `local_bug`
- `family_blocker`
- `missing_system`

Use:

- `local_bug`
  - when the issue is real but bounded to one place
- `family_blocker`
  - when repeated symptoms share one deeper cause but a reusable system design
    is not yet fully shaped
- `missing_system`
  - when the deeper cause is understood well enough to name the next reusable
    system that should be built

## Required Entry Fields

Every durable writeback must include:

- `id`
- `title`
- `class`
  - one of `local_bug`, `family_blocker`, `missing_system`
- `status`
  - one of `active`, `narrowed`, `superseded`, `resolved`, `deferred`
- `origin_surface`
  - where it was discovered, such as `cleanup/api`, `hard-01`, `medium-02`,
    `Batch B`, `review`, `sessions`
- `symptom_family`
  - the recurring observable pattern
- `evidence`
  - concrete files, runs, roadblocks, reviews, or artifacts
- `why_this_is_a_family`
  - what makes it recur beyond one bug
- `current_trust_impact`
  - what decision or proof surface remains untrustworthy
- `current_iteration_cost`
  - how it wastes time or creates wheel-spinning
- `affected_surfaces`
  - modules, stages, suites, or folders
- `next_bounded_move`
  - the immediate honest next action
- `do_not_do_yet`
  - what would be premature or over-broad

## Additional Fields For `missing_system`

If the classification is `missing_system`, the writeback must also include:

- `system_name`
- `system_goal`
- `why_existing_systems_are_insufficient`
- `minimum_useful_scope`
- `non_goals`
- `required_inputs`
- `required_outputs`
- `contract_or_schema_implications`
- `observability_or_artifact_requirements`
- `acceptance_criteria`
- `proof_of_value`
  - what would count as real improvement
- `unlock_target`
  - e.g. `hard-01`, `hard-02`, `medium trust`, `Batch B breadth`
- `stop_if`
  - what evidence would show this is the wrong next system

## Acceptance Criteria Standard

System proposals are not complete unless the acceptance criteria are concrete
enough to verify. At minimum they must answer:

- what recurring symptom should disappear
- what artifact or contract should newly exist
- what proof surface should become trustworthy
- what regression surface must remain green
- what would count as failure even if implementation landed

Prefer criteria that reference:

- concrete files or contracts
- concrete run suites
- concrete comparison or ledger evidence
- concrete review or observability outputs

## Writeback Destinations

Use the writeback in these places as appropriate:

- `.agents/ARCHITECTURAL-WEAKNESSES.md`
  - for the live weakness register
- campaign logs under `cleanup/`
  - for overnight or campaign-local continuity
- roadblock JSON under `bugs/`
  - when the blocker is already in roadblock mode
- ecosystem docs or implementation guidance
  - when the system proposal changes durable rollout guidance

Do not rely on commit history alone as the canonical writeback.

## GM Responsibilities

The parent thread as GM must:

- decide whether a finding is only local or truly a family blocker
- pressure-test the writeback against what it would itself require to take the
  next step
- use specialist agents to gather evidence, not to make the final structural
  judgment
- keep writeback bounded and evidence-backed
- update or supersede stale entries as the repo learns more

## Relationship To Hard Unlock Work

For `hard-01` and `hard-02`, this writeback is part of the unlock loop.

The correct pattern is:

1. local fix if honest
2. family-blocker writeback if the issue repeats
3. missing-system proposal if the reusable next system is clear
4. bounded implementation of that system
5. proving rerun and trust reassessment

Do not keep retrying hard suites without strengthening the writeback when the
same blocker family remains active.
