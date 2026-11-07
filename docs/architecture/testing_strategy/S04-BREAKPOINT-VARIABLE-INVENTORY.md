# S-04 Breakpoint Variable Inventory

## Purpose

This is the durable inventory for S-04 synthesis breakpoint maturity. S-04 is
currently exercised by broad gates and S-05 seam pressure, but it has no local
synthesis-owned breakpoint ladder.

## Benchmark Question

Which S-04 variables can lose, distort, overtrust, undertrust, or omit evidence
when producing user-facing API documentation?

## Inventory Fields

Every row includes owner scope, ownership type, breakpoint family, weakness
variable, current tier, target tier, fixture shape, claim ceiling,
false-progress risk, and next gap.

## Inventory Dashboard

| Category | Count | Current state | Next gap |
| --- | ---: | --- | --- |
| Stage-owned breakpoint families | 5 | all `planned/0` | first evidence-grounded synthesis fixture |
| Seam-owned breakpoint families | 2 | `S-04 -> S-05A` is `Tier 2`; `S-03 -> S-04` is `planned/0` | anchor incoming S-03 evidence boundary |
| Bottom-up window candidates | 1 | `planned/0` | build after S-03 -> S-04 and S-04 local anchors |

## Stage-Owned Variables

| owner_scope | ownership_type | breakpoint_family | weakness_variable | current_tier | target_tier | fixture_shape | claim_ceiling | false_progress_risk | next_gap |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `S-04 synthesis` | `stage-owned` | `evidence-grounded synthesis` | documentation claims remain tied to evidence rows | `planned/0` | `Tier 2` | findings/evidence packet with verified, weak, and missing support | S-04 writes evidence-grounded docs without unsupported claims | judging prose quality instead of evidence grounding | first S-04 synthesis fixture |
| `S-04 synthesis` | `stage-owned` | `missing-evidence honesty` | missing evidence is disclosed rather than filled with plausible prose | `planned/0` | `Tier 2` | packet with known unknowns and absent observations | S-04 preserves missing-evidence boundaries | treating readable docs as accurate docs | missing-evidence fixture |
| `S-04 synthesis` | `stage-owned` | `uncertainty preservation` | uncertainty survives into final API reference language | `planned/0` | `Tier 2` | mixed-confidence findings packet | S-04 preserves uncertainty in synthesis output | flattening weak/strong evidence into one tone | uncertainty fixture |
| `S-04 synthesis` | `stage-owned` | `overconfident documentation prevention` | weak inferred evidence does not become verified documentation | `planned/0` | `Tier 3` | ambiguous evidence packet with tempting but unsupported claims | S-04 avoids overconfident docs under ambiguity | testing only obviously unsupported claims | Tier 3 overconfidence fixture |
| `S-04 synthesis` | `stage-owned` | `contradiction visibility in docs` | unresolved contradictions remain visible to downstream enrichment and operators | `planned/0` | `Tier 2` | reconciled contradiction packet with expected caveat output | S-04 surfaces contradictions rather than hiding them | using S-05 provenance to compensate for S-04 omission | contradiction-visibility fixture |

## Seam-Owned Variables

| owner_scope | ownership_type | breakpoint_family | weakness_variable | current_tier | target_tier | fixture_shape | claim_ceiling | false_progress_risk | next_gap |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `S-03 -> S-04` | `seam-owned` | `reconcile-to-synthesis evidence boundary` | S-03 uncertainty reaches S-04 without claim inflation | `planned/0` | `Tier 2` | reconciled evidence packet with supported, weak, and unresolved rows | S-04 consumes reconciled evidence boundaries honestly | giving S-04 a clean hand-authored packet | seam fixture after S-03 local inventory |
| `S-04 -> S-05A` | `seam-owned` | `synthesis-to-backfill provenance` | synthesized claims enter S-05A with provenance and uncertainty intact | `Tier 2` | `Tier 3` | S-04-shaped synthesis with supported, weak, and unsupported descriptions | S-05A consumes synthesis without treating prose as proof | treating S-05A provenance as S-04 local maturity | Tier 3 synthesis/backfill ambiguity |

## Bottom-Up Window Candidates

| owner_scope | ownership_type | breakpoint_family | current_tier | target_tier | when_to_build |
| --- | --- | --- | --- | --- | --- |
| `S-03 -> S-04 -> S-05A` | `bottom-up window` | reconciliation evidence becomes bounded schema enrichment | `planned/0` | `Tier 2` | Build after S-03 -> S-04 and S-04 local synthesis anchors exist. |

## Questions This Inventory Can Answer

- Which S-04 proof gaps could make hard01 documentation look coherent but unsupported.
- Why S-04 -> S-05A seam evidence does not prove S-04 local maturity.

## Questions This Inventory Cannot Answer

- Whether S-05 backfill is mature.
- Whether final user-facing docs are globally correct.

## What The Next Suite In This Category Should Add

- First S-04 evidence-grounded synthesis fixture with missing and weak evidence.

## Pipeline Full Tier 2 Baseline V1 Overlay

`pipeline_full_tier2_baseline_v1` gives S-04 its first local baseline:

- `Tier 2`: evidence-grounded synthesis, missing-evidence honesty, and uncertainty preservation.
- `blocked_at_tier2`: contradiction visibility in docs, `S-03 -> S-04`, and `S-03 -> S-04 -> S-05A`.
- `deferred_as_tier3_shaped`: overconfident documentation prevention.
- Existing `S-04 -> S-05A` seam evidence remains Tier 2 but does not prove S-04 local maturity by itself.
