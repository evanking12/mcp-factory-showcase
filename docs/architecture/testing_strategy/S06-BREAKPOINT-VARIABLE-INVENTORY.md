# S-06 Breakpoint Variable Inventory

## Purpose

This is the durable inventory for S-06 gap-handling breakpoint maturity. S-06 is
currently a key unproven consumer because `S-05C -> S-06` is blocked at Tier 2:
S-06 lacks an explicit S-05C decision-consumer surface.

## Benchmark Question

Which S-06 variables can lose, distort, overtrust, undertrust, widen, narrow,
or defer unresolved gaps incorrectly before S-07 finalizes output?

## Inventory Fields

Every row includes owner scope, ownership type, breakpoint family, weakness
variable, current tier, target tier, fixture shape, claim ceiling,
false-progress risk, and next gap.

## Inventory Dashboard

| Category | Count | Current state | Next gap |
| --- | ---: | --- | --- |
| Stage-owned breakpoint families | 5 | all `planned/0` except unresolved S-05C caveat consumption is `blocked_at_tier2` | explicit S-05C decision consumer and first gap fixture |
| Seam-owned breakpoint families | 2 | `S-05C -> S-06` is `blocked_at_tier2`; `S-06 -> S-07` is `planned/0` | unblock S-05C decision consumption |
| Bottom-up window candidates | 1 | `blocked_at_tier2` through S-05B -> S-05C -> S-06 dependency | build only after S-05C -> S-06 is unblocked |

## Stage-Owned Variables

| owner_scope | ownership_type | breakpoint_family | weakness_variable | current_tier | target_tier | fixture_shape | claim_ceiling | false_progress_risk | next_gap |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `S-06 gaps` | `stage-owned` | `repeated gap-family recognition` | repeated unresolved items are grouped as a family rather than isolated noise | `planned/0` | `Tier 2` | gap register with repeated related unresolved targets | S-06 recognizes repeated gap families | relying on final narrative grouping | first S-06 gap-family fixture |
| `S-06 gaps` | `stage-owned` | `retry exhaustion` | exhausted retry routes become explicit unresolved gaps | `planned/0` | `Tier 2` | retry history packet with exhausted, skipped, and unsafe attempts | S-06 preserves retry exhaustion boundaries | treating no retry as no gap | retry exhaustion fixture |
| `S-06 gaps` | `stage-owned` | `clarification relevance` | generated questions map to real missing evidence | `planned/0` | `Tier 2` | unresolved evidence packet with relevant and irrelevant question candidates | S-06 emits relevant clarification questions | scoring question count instead of relevance | clarification fixture |
| `S-06 gaps` | `stage-owned` | `architecture-gap classification` | missing systems are classified separately from product failures | `planned/0` | `Tier 3` | packet with product, lane, architecture, and evidence gaps | S-06 classifies architecture gaps honestly | blaming product behavior for missing system surfaces | Tier 3 architecture-gap fixture |
| `S-06 gaps` | `stage-owned` | `unresolved S-05C caveat consumption` | S-05C caveats and MC-5 unresolved decisions are consumed explicitly | `blocked_at_tier2` | `Tier 2` | S-05C MC-5 decision artifact with selected, unsafe, deferred, and unresolved outcomes | No Tier 2 claim; explicit S-05C decision consumer is missing | counting legacy fallback as S-05C consumer maturity | add explicit consumer boundary |

## Seam-Owned Variables

| owner_scope | ownership_type | breakpoint_family | weakness_variable | current_tier | target_tier | fixture_shape | claim_ceiling | false_progress_risk | next_gap |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `S-05C -> S-06` | `seam-owned` | `chaining-to-gaps deferral` | unresolved retry outcomes and caveats remain visible to gap handling | `blocked_at_tier2` | `Tier 2` | MC-5 decision artifact consumed by S-06 | No Tier 2 claim; S-06 lacks explicit S-05C decision-consumer surface | counting S-06 fallback as handoff proof | add S-05C decision consumer |
| `S-06 -> S-07` | `seam-owned` | `gaps-to-finalize trust boundary` | knowns, unknowns, and unresolved gaps reach finalization intact | `planned/0` | `Tier 2` | gap packet with resolved, unresolved, deferred, and architecture-gap entries | S-07 receives S-06 trust boundaries intact | testing finalization with clean hand-authored knowns | S-06 -> S-07 seam fixture |

## Bottom-Up Window Candidates

| owner_scope | ownership_type | breakpoint_family | current_tier | target_tier | when_to_build |
| --- | --- | --- | --- | --- | --- |
| `S-05B -> S-05C -> S-06` | `bottom-up window` | verification and chaining outcomes become gap decisions | `blocked_at_tier2` | `Tier 2` | Blocked until `S-05C -> S-06` has explicit consumer proof. |

## Questions This Inventory Can Answer

- Why S-05C -> S-06 is a real blocker, not just a missing test.
- Which S-06 local families should be built before hard-family interpretation.

## Questions This Inventory Cannot Answer

- Whether S-06 resolves gaps correctly.
- Whether S-07 finalization closes correctly.

## What The Next Suite In This Category Should Add

- Explicit S-05C decision consumer boundary in S-06, then a Tier 2 seam fixture.

## Pipeline Full Tier 2 Baseline V1 Overlay

`pipeline_full_tier2_baseline_v1` keeps S-06 mostly blocked:

- `blocked_at_tier2`: repeated gap-family recognition, retry exhaustion, clarification relevance, unresolved S-05C caveat consumption, `S-05C -> S-06`, `S-06 -> S-07`, and `S-05B -> S-05C -> S-06`.
- `deferred_as_tier3_shaped`: architecture-gap classification.
- Primary unlock remains an explicit S-05C decision-consumer surface.
