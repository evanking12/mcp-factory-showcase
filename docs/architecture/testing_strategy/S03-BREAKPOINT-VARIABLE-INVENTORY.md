# S-03 Breakpoint Variable Inventory

## Purpose

This is the durable inventory for S-03 reconciliation breakpoint maturity.
S-03 currently has seam-owned evidence through `S-02C -> S-03`, but no local
S-03 contradiction ladder.

## Benchmark Question

Which S-03 variables can lose, distort, overtrust, undertrust, defer, or
misclassify probe evidence before S-04 synthesis writes user-facing claims?

## Inventory Fields

Every row includes owner scope, ownership type, breakpoint family, weakness
variable, current tier, target tier, fixture shape, claim ceiling,
false-progress risk, and next gap.

## Inventory Dashboard

| Category | Count | Current state | Next gap |
| --- | ---: | --- | --- |
| Stage-owned breakpoint families | 5 | all `planned/0` | first contradiction/reconciliation fixture |
| Seam-owned breakpoint families | 3 | `S-02C -> S-03` has two `Tier 2` rows; `S-03 -> S-04` is `planned/0` | local S-03 maturity before stronger synthesis claims |
| Bottom-up window candidates | 1 | `planned/0` | build after S-03 local and S-03 -> S-04 seam anchors |

## Stage-Owned Variables

| owner_scope | ownership_type | breakpoint_family | weakness_variable | current_tier | target_tier | fixture_shape | claim_ceiling | false_progress_risk | next_gap |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `S-03 reconcile` | `stage-owned` | `contradictory evidence handling` | contradictory probe, static, and finding evidence is reconciled without inventing certainty | `planned/0` | `Tier 2` | packet with one supported contradiction, one weak contradiction, and one missing observation | S-03 classifies contradictions with bounded evidence | using S-02C consumability as S-03 maturity | first S-03 contradiction fixture |
| `S-03 reconcile` | `stage-owned` | `missing-observation deferral` | absence of probe evidence remains deferral, not success or final failure | `planned/0` | `Tier 2` | missing/blocked observation packet with expected deferral | S-03 defers missing observations honestly | treating no error as success | deferral fixture |
| `S-03 reconcile` | `stage-owned` | `repeated unresolved status` | repeated unresolved findings remain visible and attributable | `planned/0` | `Tier 2` | repeated unresolved finding packet across multiple evidence sources | S-03 preserves repeated unresolved status | collapsing repeated unresolved into generic failure | unresolved-status fixture |
| `S-03 reconcile` | `stage-owned` | `false repair prevention` | weak positive evidence does not repair a finding without support | `planned/0` | `Tier 3` | ambiguous mixed-positive fixture | S-03 avoids false repair under ambiguity | making weak positives obviously invalid | Tier 3 false-repair fixture |
| `S-03 reconcile` | `stage-owned` | `wrong blocker attribution` | unresolved work is attributed to stage, seam, lane, or architecture gap honestly | `planned/0` | `Tier 3` | packet with product, lane, missing-evidence, and architecture-gap causes | S-03 assigns blocker ownership correctly | blaming downstream synthesis for S-03 classification errors | blocker-attribution fixture |

## Seam-Owned Variables

| owner_scope | ownership_type | breakpoint_family | weakness_variable | current_tier | target_tier | fixture_shape | claim_ceiling | false_progress_risk | next_gap |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `S-02C -> S-03` | `seam-owned` | `probe evidence consumability` | S-03 consumes durable S-02C evidence without hidden memory shortcuts | `Tier 2` | `Tier 3` | S-02C durable evidence packet with success-like and missing rows | S-03 consumes S-02C durable probe evidence boundaries under medium pressure | treating this as S-03 local contradiction maturity | Tier 3 contradictory packet seam |
| `S-02C -> S-03` | `seam-owned` | `missing-observation deferral` | missing or blocked observations stay visible through reconciliation | `Tier 2` | `Tier 3` | persisted packet with missing, blocked, and unresolved evidence | missing probe evidence is deferred honestly into reconciliation | counting absence as success | Tier 3 absence/contradiction seam |
| `S-03 -> S-04` | `seam-owned` | `reconcile-to-synthesis evidence boundary` | reconciled evidence and uncertainty reach synthesis without confidence laundering | `planned/0` | `Tier 2` | reconciled finding packet with supported, weak, unresolved, and contradictory rows | S-04 receives S-03 uncertainty boundaries intact | testing S-04 with hand-authored clean findings | S-03 -> S-04 seam fixture |

## Bottom-Up Window Candidates

| owner_scope | ownership_type | breakpoint_family | current_tier | target_tier | when_to_build |
| --- | --- | --- | --- | --- | --- |
| `S-02C -> S-03 -> S-04` | `bottom-up window` | durable probe evidence becomes bounded synthesis input | `planned/0` | `Tier 2` | Build after S-03 local contradiction and S-03 -> S-04 seam anchors exist. |

## Questions This Inventory Can Answer

- Which S-03 local proof is still absent despite S-02C seam evidence.
- What failures hard01 should classify as reconciliation weakness.

## Questions This Inventory Cannot Answer

- Whether S-04 synthesis is honest.
- Whether S-03 is Tier 2 or Tier 3 locally.

## What The Next Suite In This Category Should Add

- First S-03 contradiction and missing-observation local fixture.

## Pipeline Full Tier 2 Baseline V1 Overlay

`pipeline_full_tier2_baseline_v1` makes S-03 failure explicit:

- `Tier 2`: missing-observation deferral, backed by focused reconciliation/seam evidence.
- `failed_tier2`: contradictory evidence handling lacks a local contradiction classification surface.
- `blocked_at_tier2`: repeated unresolved status and `S-03 -> S-04`.
- `deferred_as_tier3_shaped`: false repair prevention and wrong blocker attribution.
- `blocked_at_tier2`: `S-02C -> S-03 -> S-04` bottom-up window until the S-03 -> S-04 seam exists.
