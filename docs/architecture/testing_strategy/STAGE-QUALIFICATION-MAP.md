# Stage Qualification Map

## Purpose

This map decides whether a stage is ready for breakpoint-family inventory and
tiered proving, or whether it first needs structural work.

It is not a breakpoint scorecard. Breakpoint maturity lives in
[`STAGE-PROVING-MAP.md`](STAGE-PROVING-MAP.md), and tier definitions live in
[`BREAKPOINT-TIER-RUBRIC.md`](BREAKPOINT-TIER-RUBRIC.md).

Qualification answers one question:

`Is this stage observable, attributable, artifact-owned, seam-aware, compatibility-safe, and proving-map-ready enough to strengthen?`

## Source Synchronization

Keep this map synchronized with:

| Surface | Role |
| --- | --- |
| `api/pipeline/s*/LIVE-CONTRACT.md` | Stage semantic obligation and handoff rule. |
| `api/pipeline/s*/FAMILY-BLOCKERS.md` | Known blocker families and architecture gaps. |
| `api/pipeline/s*/TRACE.md` | Red/yellow/gray/green ownership and expected homes. |
| `docs/architecture/testing_strategy/STAGE-PROVING-MAP.md` | Breakpoint ownership, current tier, target tier, and claim ceiling. |
| `configs/regression/check_registry.json` | Path-aware governance and proving check routing. |

## Qualification Rubric

Each stage or substage row uses these values:

- `pass`: enough evidence exists for the current claim.
- `partial`: the surface exists, but is incomplete or not strong enough to be the next proving anchor by itself.
- `missing`: the surface is absent or not reviewable.
- `deferred`: intentionally not owned by this stage or not implemented yet.

Required fields:

| Field | Meaning |
| --- | --- |
| `clear_obligation` | The stage has one coherent semantic responsibility. |
| `runtime_visible_identity` | Failures, statuses, or checkpoints identify the stage under its own name. |
| `owned_artifacts` | The stage emits or owns reviewable artifacts tied to its obligation. |
| `compatibility_surfaces` | Legacy aliases, downstream consumers, and fallback paths are understood. |
| `operator_github_observability` | GitHub summaries, checkpoint logs, or operator artifacts localize stage failures. |
| `adjacent_seams_known` | Producer and consumer seams are named and claim ceilings are clear. |
| `proving_map_row` | The stage has a row in `STAGE-PROVING-MAP.md`. |
| `split_pressure` | The map states whether the stage is cohesive or likely owns too much. |

Qualification results:

- `stage_quality_ready`: ready for breakpoint inventory and ladder work.
- `needs_internal_ownership_split`: code ownership is too blended to test cleanly.
- `needs_runtime_visible_split`: code may be organized, but failures are not separately attributable.
- `needs_artifact_or_session_ownership`: stage cannot yet be audited from durable outputs.
- `needs_observability_hardening`: GitHub/operator surfaces do not localize failures.
- `needs_proving_map_completion`: stage is usable but lacks breakpoint-family clarity.
- `strategic_split_candidate`: stage likely owns multiple semantic obligations and should be split in a later campaign.

## S-00 Reference Standard

S-00 is the current reference because its split required more than file
organization:

| Standard layer | Evidence |
| --- | --- |
| Internal ownership split | `setup_baseline.py`, `static_evidence.py`, and `admission_handoff.py` own separate responsibilities. |
| Runtime-visible split | `s00_setup_baseline`, `s00_static_evidence`, and `s00_admission_handoff` are checkpoint/runtime identities. |
| Artifact/session compatibility | Legacy `s00_setup` and `stage-00-setup` surfaces remain compatible while aliases expose future homes. |
| Packet usefulness | S-00 admitted targets can affect bounded S-01 probe ordering while fallback remains intact. |
| Static enrichment | Normalized static enrichment is additive and non-authoritative. |
| Observability and CI | Stage Breakpoint Checks can route stage-owned proving suites. |
| Tiered proving | S-00A/B/C each have one stage-owned breakpoint family at Tier 2. |

This is the bar for calling a future split useful: the new stage identity must
be observable, attributable, compatible, artifact-owned, and testable against
its obligation.

## Stage Qualification Scorecard

| Scope | clear_obligation | runtime_visible_identity | owned_artifacts | compatibility_surfaces | operator_github_observability | adjacent_seams_known | proving_map_row | split_pressure | qualification_result | Next action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `S-00A setup_baseline` | pass | pass | pass | pass | pass | pass | pass | partial | stage_quality_ready | Keep as reference; next only if Tier 3 setup ambiguity becomes highest value. |
| `S-00B static_evidence` | pass | pass | pass | pass | pass | pass | pass | partial | stage_quality_ready | Keep as reference; next only if Tier 3 static-thin evidence becomes highest value. |
| `S-00C admission_handoff` | pass | pass | pass | pass | pass | pass | pass | partial | stage_quality_ready | Keep as reference; coordinate only if seam pressure proves narrowing judgment is needed. |
| `S-01 unlock` | pass | pass | partial | pass | partial | pass | pass | partial | stage_quality_ready | Build unlock-owned breakpoint variable inventory before splitting. |
| `S-02 parent probe` | pass | pass | partial | pass | pass | pass | pass | partial | stage_quality_ready | Keep `s02_probe` as compatibility parent for the split S-02 runtime checkpoints. |
| `S-02A probe_ordering` | pass | pass | partial | pass | pass | pass | pass | partial | stage_quality_ready | Build ordering/prerequisite-state breakpoint inventory after hosted split validation. |
| `S-02B invocation_execution` | pass | pass | partial | pass | pass | pass | pass | partial | stage_quality_ready | Build argument construction, lane/runtime classification, and overtrust breakpoint inventory. |
| `S-02C evidence_capture` | pass | pass | partial | pass | pass | pass | pass | partial | stage_quality_ready | Build evidence durability, finding persistence, and downstream consumability breakpoint inventory. |
| `S-03 reconcile` | pass | pass | partial | partial | partial | pass | pass | partial | stage_quality_ready | Build contradiction and blocker-attribution breakpoint inventory. |
| `S-04 synthesis` | pass | pass | partial | partial | partial | pass | pass | partial | stage_quality_ready | Build evidence-grounding and overclaim-prevention breakpoint inventory. |
| `S-05 parent enrichment` | pass | pass | partial | pass | pass | pass | pass | partial | stage_quality_ready | Keep `s05_enrichment` as compatibility parent for the split S-05 runtime checkpoints. |
| `S-05A schema_backfill` | pass | pass | partial | pass | pass | pass | pass | partial | stage_quality_ready | Build schema provenance, prose-as-proof prevention, and compatibility breakpoint inventory after hosted split validation. |
| `S-05B verification_replay` | pass | pass | partial | pass | pass | pass | pass | partial | stage_quality_ready | Build direct replay truth, state-effect verification, bridge classification, and finding-patch honesty breakpoint inventory. |
| `S-05C read_to_write_chaining` | pass | pass | partial | pass | pass | pass | pass | partial | stage_quality_ready | Build MC-5 value extraction, retry containment, and weak-ID non-overtrust breakpoint inventory. |
| `S-06 gaps` | pass | pass | partial | partial | partial | pass | pass | partial | stage_quality_ready | Build retry exhaustion, clarification relevance, and architecture-gap breakpoint inventory. |
| `S-07 finalize` | pass | pass | pass | partial | pass | pass | pass | partial | stage_quality_ready | Build final trust-boundary and close-path reliability breakpoint inventory. |

## Adjacent Seam Qualification

| Seam | Producer | Consumer | Known handoff | Qualification | Next action |
| --- | --- | --- | --- | --- | --- |
| `S-00A -> S-00B` | setup baseline | static evidence | vocab, sentinel, and prior context feeding static extraction | stage_quality_ready | Add bottom-up window only if static evidence cannot explain setup-derived weakness. |
| `S-00B -> S-00C` | static evidence | admission handoff | static analysis and enrichment feeding packet admission | stage_quality_ready | Add bottom-up window if static evidence is honest but admission misuses it. |
| `S-00C -> S-01` | admission handoff | unlock | `s01_handoff_packet.json` target guidance and fallback | stage_quality_ready | Raise seam from Tier 1 when medium/hard admission pressure becomes the highest-value blocker. |
| `S-01 -> S-02A` | unlock | probe ordering | write-mode condition and probe admission | needs_proving_map_completion | Inventory unlock-to-ordering handoff variables. |
| `S-02A -> S-02B` | probe ordering | invocation execution | ordered queue and prerequisite-state plan feeding execution | needs_proving_map_completion | Inventory ordering-to-execution loss or overtrust. |
| `S-02B -> S-02C` | invocation execution | evidence capture | raw observations feeding durable evidence persistence | needs_proving_map_completion | Inventory raw-observation durability and persistence mismatch. |
| `S-02C -> S-03` | evidence capture | reconcile | runtime observations and contradiction inputs | needs_proving_map_completion | Inventory probe evidence consumability and missing-observation deferral. |
| `S-03 -> S-04` | reconcile | synthesis | reconciled evidence and confidence boundaries | needs_proving_map_completion | Inventory low-confidence transfer and contradiction visibility. |
| `S-04 -> S-05A` | synthesis | schema backfill | synthesized claims with provenance caveats | needs_proving_map_completion | Inventory prose-as-proof leakage. |
| `S-05A -> S-05B` | schema backfill | verification replay | enriched schema and backfill provenance into verification | needs_proving_map_completion | Inventory enrichment-as-proof leakage. |
| `S-05B -> S-05C` | verification replay | read-to-write chaining | verified read evidence and caveats into MC-5 | needs_proving_map_completion | Inventory verified/unverified confusion. |
| `S-05C -> S-06` | read-to-write chaining | gaps | unresolved retry outcomes, caveats, and verification status | needs_proving_map_completion | Inventory caveat loss and unresolved-item widening. |
| `S-05 -> S-06` | enrichment compatibility parent | gaps | legacy unresolved targets, caveats, and verification status | compatibility_parent | Preserved as alias for S-05C -> S-06 while breakpoint work targets the child seam. |
| `S-06 -> S-07` | gaps | finalize | knowns, unknowns, and trust boundaries | needs_proving_map_completion | Inventory finalization input mismatch and trust-boundary loss. |

## Split Readiness Ranking

Scoring uses `1` to `10`, where higher means the next campaign would likely
produce clearer diagnosis or stronger architecture.

| Candidate | diagnostic_value | split_pressure | downstream_poison_risk | observability_gap | fixture_proving_cost | Priority | Recommended next campaign |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `S-02 probe` | 10 | 9 | 10 | 7 | 5 | completed | Runtime expansion implemented through `s02_runtime_stage_expansion_v1`; next branch is S-02 breakpoint variable inventory after hosted validation. |
| `S-05 enrichment` | 8 | completed | 8 | completed | 6 | completed | Runtime expansion implemented through `s05_runtime_stage_expansion_v1`; next branch is S-05 breakpoint variable inventory after hosted validation. |
| `S-01 unlock` | 8 | 5 | 9 | 5 | 8 | 3 | Breakpoint variable inventory: unlock target prioritization, fallback, overtrust prevention, and candidate exhaustion. |

## Current Decision

The next campaign should not be another S-00 structural campaign by default.
S-00A/B/C are qualified enough to serve as the reference standard.

Recommended next branch:

1. Create `s05_breakpoint_variable_inventory_v1` after hosted S-05 runtime
   expansion validation.
2. Preserve `s05_enrichment` compatibility while treating `s05_schema_backfill`,
   `s05_verification_replay`, and `s05_read_to_write_chaining` as full
   runtime-visible stages.
3. Defer S-05 breakpoint ladders until the variable inventory is explicit.

## Claim Ceiling

This map is Tier 0 governance and stage-readiness classification only. It does
not claim breakpoint maturity, product correctness, or broad non-regression.
