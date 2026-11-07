# S-00 Breakpoint Variable Inventory

## Purpose

This is the durable inventory for S-00 breakpoint maturity after the runtime
split into `S-00A setup_baseline`, `S-00B static_evidence`, and
`S-00C admission_handoff`.

Rows stay at their current tier until their own stage, seam, or bottom-up
fixtures exist. This inventory does not promote any new row.

## Benchmark Question

Which S-00 variables can lose, distort, overtrust, undertrust, narrow, widen,
or defer setup/static evidence incorrectly before S-01 consumes it?

## Inventory Fields

Every row includes owner scope, ownership type, breakpoint family, weakness
variable, current tier, target tier, fixture shape, claim ceiling,
false-progress risk, and next gap.

## Inventory Dashboard

| Category | Count | Current state | Next gap |
| --- | ---: | --- | --- |
| Stage-owned breakpoint families | 12 | 3 are `Tier 2`; 9 remain `planned/0` or Tier 3-targeted | expand beyond one anchor per S-00 runtime stage |
| Seam-owned breakpoint families | 3 | `S-00C -> S-01 admission pressure` is `Tier 1`; internal seams remain `planned/0` | raise admission seam to Tier 2 before coordinator work |
| Bottom-up window candidates | 1 | `planned/0` | build only after adjacent stage/seam anchors justify composition |

## Stage-Owned Variables

| owner_scope | ownership_type | breakpoint_family | weakness_variable | current_tier | target_tier | fixture_shape | claim_ceiling | false_progress_risk | next_gap |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `S-00A setup_baseline` | `stage-owned` | `sentinel/vocab baseline` | hinted vocab and sentinel evidence are preserved without inventing static evidence | `Tier 2` | `Tier 3` | medium compiled-context fixture with noisier prior hints and multiple explicit sentinels | S-00A preserves setup baseline under medium context pressure | treating setup success as static evidence truth | Tier 3 conflicting-hint setup fixture |
| `S-00A setup_baseline` | `stage-owned` | `prior-context overtrust` | weak prior hints do not become authoritative stage truth | `planned/0` | `Tier 2` | prior-context packet with misleading, absent, and supported hints | S-00A keeps prior hints bounded | counting downstream fallback as setup maturity | Tier 2 prior-context overtrust fixture |
| `S-00A setup_baseline` | `stage-owned` | `thin setup evidence` | sparse setup evidence produces honest uncertainty, not fake readiness | `planned/0` | `Tier 3` | static-thin setup fixture with deterministic fallback expectation | S-00A defers thin setup evidence honestly | labeling no evidence as a clean baseline | Tier 3 thin-evidence fixture |
| `S-00B static_evidence` | `stage-owned` | `callable inventory richness` | callable inventory captures meaningful exports without runtime claims | `Tier 2` | `Tier 3` | medium compiled DLL with callable pressure and distractor exports | S-00B extracts bounded callable inventory under medium pressure | treating inventory as verified behavior | Tier 3 ambiguous callable fixture |
| `S-00B static_evidence` | `stage-owned` | `static string thinness` | weak or absent strings stay reviewable rather than becoming target proof | `planned/0` | `Tier 3` | static-thin fixture with weak/conflicting strings | S-00B reports string thinness honestly | overvaluing one string hit | Tier 3 static-thin pressure |
| `S-00B static_evidence` | `stage-owned` | `enrichment provenance` | enrichment records whether data came from scanner, optional Ghidra, or fallback | `planned/0` | `Tier 2` | enrichment packet with mixed source availability | S-00B keeps static enrichment provenance reviewable | treating optional enrichment as authoritative | Tier 2 provenance fixture |
| `S-00B static_evidence` | `stage-owned` | `raw-overread prevention` | static inventory does not overread broad names into product semantics | `planned/0` | `Tier 3` | hard naming fixture with misleading broad callable names | S-00B avoids overclaiming from raw static names | scoring broad inventory as semantic understanding | Tier 3 overread fixture |
| `S-00C admission_handoff` | `stage-owned` | `admission capping` | target admission stays bounded under broad static guidance | `Tier 2` | `Tier 3` | medium compiled pressure with broad candidates and deterministic cap expectations | S-00C caps admitted targets under medium pressure | using cap existence as correctness proof | Tier 3 broad/ambiguous admission fixture |
| `S-00C admission_handoff` | `stage-owned` | `weak-target non-overtrust` | weak targets remain deferred or ambiguous rather than admitted as strong | `planned/0` | `Tier 3` | conflicting weak-target fixture | S-00C avoids overtrusting weak targets | admitting obvious good targets only | Tier 3 weak-target fixture |
| `S-00C admission_handoff` | `stage-owned` | `deferred evidence honesty` | deferred evidence remains visible to operators and consumers | `planned/0` | `Tier 2` | handoff packet with admitted, deferred, and ambiguous evidence | S-00C preserves deferred evidence boundaries | dropping deferred evidence because S-01 fallback works | Tier 2 deferral fixture |
| `S-00C admission_handoff` | `stage-owned` | `cross-DLL hint deferral` | cross-DLL hints are not treated as local proof | `planned/0` | `Tier 3` | cross-DLL hint packet with local/non-local ambiguity | S-00C defers cross-DLL hints honestly | using cross-DLL names as direct local targets | Tier 3 cross-DLL fixture |

## Seam-Owned Variables

| owner_scope | ownership_type | breakpoint_family | weakness_variable | current_tier | target_tier | fixture_shape | claim_ceiling | false_progress_risk | next_gap |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `S-00A -> S-00B` | `seam-owned` | `setup-to-static handoff` | vocab/sentinel setup feeds static evidence without overwriting scanner truth | `planned/0` | `Tier 2` | setup packet plus static fixture with supported and unsupported hints | static evidence consumes setup hints as bounded context | testing S-00B directly without setup handoff | seam fixture after S-00A/S-00B local rows mature |
| `S-00B -> S-00C` | `seam-owned` | `static-to-admission provenance` | static evidence reaches admission with source and confidence intact | `planned/0` | `Tier 2` | static evidence packet with weak, strong, deferred, and ambiguous rows | admission preserves static provenance | admitting targets without checking source strength | seam fixture after provenance row exists |
| `S-00C -> S-01` | `seam-owned` | `admission pressure` | admitted packet targets guide S-01 while fallback remains intact | `Tier 1` | `Tier 3` | Tier 2 medium admission fixture; Tier 3 thin/conflicting fixture | handoff survives one easy compiled pressure case | treating this as all S-00 strength | Tier 2 medium admission seam |

## Bottom-Up Window Candidates

| owner_scope | ownership_type | breakpoint_family | current_tier | target_tier | when_to_build |
| --- | --- | --- | --- | --- | --- |
| `S-00B -> S-00C -> S-01` | `bottom-up window` | static evidence becomes bounded admission and unlock guidance | `planned/0` | `Tier 2` | Build after S-00B provenance and S-00C admission pressure have stronger anchors. |

## Questions This Inventory Can Answer

- Which S-00 variables are stage-owned versus seam-owned.
- Which S-00 claims already have narrow fixture-backed evidence.
- Which S-00 weaknesses should be expected before hard-family comparison.

## Questions This Inventory Cannot Answer

- Whether all of S-00 is Tier 2 or Tier 3.
- Whether S-01 unlock is locally mature.
- Whether a post-S-00 coordinator is needed or correct.

## What The Next Suite In This Category Should Add

- Tier 2 `S-00C -> S-01` medium admission pressure.
- S-00B static provenance pressure before any bottom-up S-00 window.

## Pipeline Full Tier 2 Baseline V1 Overlay

`pipeline_full_tier2_baseline_v1` preserves existing Tier 2 S-00A/B/C anchors
and classifies the remaining S-00 rows:

- `blocked_at_tier2`: prior-context overtrust, enrichment provenance, deferred evidence honesty, `S-00A -> S-00B`, `S-00B -> S-00C`, and `S-00B -> S-00C -> S-01`.
- `deferred_as_tier3_shaped`: thin setup evidence, static string thinness, raw-overread prevention, weak-target non-overtrust, and cross-DLL hint deferral.
- `Tier 1`: `S-00C -> S-01 admission pressure` remains Tier 1 until medium admission seam pressure is built.
