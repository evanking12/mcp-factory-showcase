# S-01 Breakpoint Variable Inventory

## Purpose

This is the durable inventory for S-01 unlock breakpoint maturity. S-01 has
seam participation evidence, but no unlock-owned ladder yet.

## Benchmark Question

Which S-01 variables can lose, distort, overtrust, undertrust, widen, narrow,
or defer unlock evidence incorrectly before S-02A orders probe work?

## Inventory Fields

Every row includes owner scope, ownership type, breakpoint family, weakness
variable, current tier, target tier, fixture shape, claim ceiling,
false-progress risk, and next gap.

## Inventory Dashboard

| Category | Count | Current state | Next gap |
| --- | ---: | --- | --- |
| Stage-owned breakpoint families | 5 | all `planned/0`; S-01 has seam participation only | first unlock-owned compiled fixture |
| Seam-owned breakpoint families | 2 | `S-00C -> S-01` is `Tier 1`; `S-01 -> S-02A` is `Tier 2` through S-02 grounding | build S-01 local anchors before stronger seams |
| Bottom-up window candidates | 1 | `planned/0` | build only after S-01 and S-02A local anchors are sufficient |

## Stage-Owned Variables

| owner_scope | ownership_type | breakpoint_family | weakness_variable | current_tier | target_tier | fixture_shape | claim_ceiling | false_progress_risk | next_gap |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `S-01 unlock` | `stage-owned` | `unlock target prioritization` | admitted init/write candidates are prioritized without suppressing fallback | `planned/0` | `Tier 2` | compiled fixture with valid unlock target, fallback candidates, and distractors | S-01 prioritizes admitted unlock targets while preserving fallback | using S-02A ordering proof as S-01 proof | first S-01 unlock-owned Tier 1/Tier 2 fixture |
| `S-01 unlock` | `stage-owned` | `fallback under weak guidance` | weak or missing S-00 guidance does not stall unlock probing | `planned/0` | `Tier 2` | packet with missing, thin, and malformed target guidance | S-01 falls back honestly when guidance is weak | counting any later probe success as fallback maturity | weak-guidance fallback fixture |
| `S-01 unlock` | `stage-owned` | `overtrust prevention` | weak static/admission hints do not become forced unlock truth | `planned/0` | `Tier 3` | ambiguous unlock fixture with misleading target names | S-01 avoids overtrusting weak unlock hints | making the bad target obvious | Tier 3 ambiguity fixture |
| `S-01 unlock` | `stage-owned` | `candidate exhaustion` | exhausted unlock candidates remain reviewable rather than disappearing | `planned/0` | `Tier 2` | fixture with finite failed candidates and deterministic exhaustion result | S-01 reports candidate exhaustion with fallback boundary | treating no unlock as no problem | exhaustion fixture |
| `S-01 unlock` | `stage-owned` | `bad-unlock containment` | bad unlock evidence does not poison downstream ordering | `planned/0` | `Tier 3` | fixture with plausible but wrong unlock signal | S-01 contains bad unlock evidence before S-02A | blaming S-02A for malformed unlock input | hard bad-unlock fixture |

## Seam-Owned Variables

| owner_scope | ownership_type | breakpoint_family | weakness_variable | current_tier | target_tier | fixture_shape | claim_ceiling | false_progress_risk | next_gap |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `S-00C -> S-01` | `seam-owned` | `admission pressure` | admitted packet targets alter bounded unlock work while fallback remains intact | `Tier 1` | `Tier 3` | medium admission fixture with noise, capping, and fallback | handoff survives one easy compiled pressure case | treating seam evidence as unlock-owned maturity | Tier 2 seam fixture |
| `S-01 -> S-02A` | `seam-owned` | `unlock-to-ordering handoff` | unlock evidence guides S-02A without dropping fallback candidates | `Tier 2` | `Tier 3` | medium compiled fixture with valid unlock, blocked write, and fallback candidates | unlock evidence can guide S-02A ordering under medium pressure | claiming S-01 local maturity from the handoff | Tier 3 malformed unlock handoff |

## Bottom-Up Window Candidates

| owner_scope | ownership_type | breakpoint_family | current_tier | target_tier | when_to_build |
| --- | --- | --- | --- | --- | --- |
| `S-00C -> S-01 -> S-02A` | `bottom-up window` | admitted target becomes unlock guidance and safe ordering | `planned/0` | `Tier 2` | Build after S-01 has at least one unlock-owned anchor. |

## Questions This Inventory Can Answer

- Why S-01 is not yet locally Tier 2 despite adjacent seam evidence.
- Which unlock variables should be built before hard-family comparison if S-01 becomes the weakest link.

## Questions This Inventory Cannot Answer

- Whether S-01 unlock works broadly.
- Whether S-02A ordering maturity proves S-01 maturity.

## What The Next Suite In This Category Should Add

- First S-01 unlock-owned Tier 1/Tier 2 compiled fixture for target prioritization and fallback.

## Pipeline Full Tier 2 Baseline V1 Overlay

`pipeline_full_tier2_baseline_v1` classifies S-01 as a partial local baseline:

- `Tier 2`: unlock target prioritization and fallback under weak guidance.
- `blocked_at_tier2`: candidate exhaustion and `S-00C -> S-01 -> S-02A`.
- `deferred_as_tier3_shaped`: overtrust prevention and bad-unlock containment.
- Existing seam evidence remains separate: `S-01 -> S-02A` is Tier 2 and `S-00C -> S-01` remains Tier 1.
