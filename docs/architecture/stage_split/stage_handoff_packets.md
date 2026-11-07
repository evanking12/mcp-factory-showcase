# Stage Handoff Packets

> Architecture doctrine surface.
> This file defines the packet shape and role boundaries for stage handoff,
> review, and admission or flow-control decisions.
> It is not a code contract yet, but it is intended implementation doctrine.

## Purpose

Stages should not hand off raw findings.

Stages should hand off organized conditions that let the next stage do its own
job without becoming an archaeology stage.

The point is not "more metadata."
The point is to keep each stage relevant to its own task and to stop later
stages from re-sorting a giant upstream pile.

## Core Law

Stages produce usable next-stage conditions, not archaeology burdens.

Every stage should hand off something narrower than what it internally handled.

That means the stage does not simply dump all findings forward.
It narrows what is:

- active now
- deferred for later
- still ambiguous
- non-authoritative
- worth targeting next

## Packet Shape

The standard packet shape is:

- `stage_outputs`
  - the actual artifacts and findings produced
- `carry_forward`
  - what the next stage should actively use now
- `deferred`
  - what exists but should not drive the next step yet
- `ambiguities`
  - unresolved uncertainties the next stage must treat carefully
- `review_verdict`
  - whether the stage met its own contract
  - whether handoff is legal
  - what is still weak
- `coordination_decision`
  - the coordinator-owned admission and flow decision
  - should contain at least:
    - `flow_outcome`
      - `stay`
      - `advance`
      - `defer_and_advance`
      - `bounded_repair`
    - `admitted_forward`
      - what subset the next stage should actively receive
    - `kept_deferred`
      - what remains parked
    - `revived_from_deferred`
      - anything reactivated and why
    - `target_narrowing`
      - the exact surfaces, functions, or questions that remain active next
    - `admission_risk`
      - what remains weak or should not be overread
- `next_stage_targets`
  - the exact surfaces, functions, or questions the next stage should focus on
- `do_not_overread`
  - what the stage discovered that is still non-authoritative

This is doctrine for the intended packet contract, not an implementation API.

## Admission Organization

A pure flow-control coordinator is too weak.

It can say `advance` or `stay`, but it cannot prevent the next stage from
receiving too much, too little, or the wrong slice.

A semantic organizer is too broad.

If the coordinator starts reinterpreting raw findings from scratch, it turns
into a hidden rescue stage and weakens upstream contract ownership.

The intended middle role is admission organization:

- packet admission
- packet reduction
- deferred-surface parking
- justified revival from deferred
- target narrowing
- bounded routing when the packet shape is not good enough yet

## Role Boundaries

### Stage

- produces the candidate handoff packet
- performs first-pass organization of its own findings
- owns its own findings and local contract
- does not decide semantic truth beyond its own bounded seam

### Reviewer

- judges whether the stage met its own contract
- judges whether handoff is legal
- judges whether the organization is sufficient for honest handoff
- remains read-only
- does not own semantic truth

### Coordinator

- decides flow control and admission organization
- may choose:
  - `stay`
  - `advance`
  - `defer_and_advance`
  - `bounded_repair`
- organizes what is admitted across the stage boundary by:
  - narrowing what moves forward now
  - preserving what stays deferred
  - reviving deferred material when justified
  - tightening next-stage targets
- does not become a semantic truth owner
- does not reinterpret raw findings from scratch
- does not become a giant rescue bucket

## Flow Decisions

### `stay`

- remain in the current stage because the stage does not yet have enough
  trustworthy output to hand off
- keep admission narrow and do not widen the next-stage packet prematurely

### `advance`

- move to the next stage because the handoff packet is sufficient as-is
- admit the current narrowed packet forward without reviving extra material

### `defer_and_advance`

- move forward, but only with a narrowed active packet while keeping some
  material explicitly parked
- record what was kept deferred and what exact active slice was admitted

### `bounded_repair`

- route back for one local corrective pass instead of broadening or silently
  pushing weak output forward
- tie the repair request to packet shape, admission quality, or target
  narrowing weakness

## Anti-Patterns

- vague "organization stage" with no single job
- coordinator as rescue bucket
- coordinator reinterpreting raw findings from scratch
- coordinator doing semantic cleanup for weak upstream stages
- reviewer as semantic authority
- `deferred` as a junk drawer for "things we didn't understand"
- packet admission logic hidden in chat instead of written into the packet
- next stage forced to reinterpret everything from scratch
- packet growth that becomes richer but less decision-bearing

## Downstream Law

Every stage should hand off something narrower than what it internally handled.

If a stage cannot do that, it is still too blended, too early, or too weakly
contracted.

If a later stage keeps rescuing it, the earlier stage still lacks a real
handoff contract.
