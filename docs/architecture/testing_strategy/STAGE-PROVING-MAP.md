# Stage Proving Map

## Purpose

This is the live central scorecard for strengthening stages, seams,
coordinators, and short bottom-up windows without turning every failure into a
broad suite mystery.

Tier definitions live in
[`BREAKPOINT-TIER-RUBRIC.md`](BREAKPOINT-TIER-RUBRIC.md). This file does not
redefine the ladder. It records current proving posture, missing fixtures, and
the next useful breakpoint families.

Stage structural readiness lives in
[`STAGE-QUALIFICATION-MAP.md`](STAGE-QUALIFICATION-MAP.md). Do not use this
scorecard to claim a stage is ready for proving if the qualification map says
it needs structural work first.

`Easy01`, `Medium01`, and hard-family suites remain important cohesion and
baseline surfaces. They do not, by themselves, prove that every stage is
semantically strong. This map decides where narrower stage, seam, coordinator,
and breakpoint suites are needed before broader suites can be interpreted
cleanly.

## Source Synchronization

Keep these surfaces synchronized:

| Surface | Role |
| --- | --- |
| `LIVE-CONTRACT.md` | Semantic obligation source for each stage. |
| `FAMILY-BLOCKERS.md` | Blocker-family source for each stage. |
| `TRACE.md` | Red/yellow/gray/green ownership source. |
| `STAGE-QUALIFICATION-MAP.md` | Structural readiness map that decides whether a stage is qualified for breakpoint inventory or needs split/observability/artifact work first. |
| `STAGE-PROVING-MAP.md` | Central proving scorecard that joins obligation, blocker families, ownership type, current tier, target tier, and claim ceiling. |
| `S00-BREAKPOINT-VARIABLE-INVENTORY.md` | S-00-owned variable inventory after the S-00 runtime split. |
| `S01-BREAKPOINT-VARIABLE-INVENTORY.md` | S-01 unlock variable inventory and first local fixture candidates. |
| `S02-BREAKPOINT-VARIABLE-INVENTORY.md` | S-02-owned variable inventory and first fixture ranking after the S-02 runtime split. |
| `S03-BREAKPOINT-VARIABLE-INVENTORY.md` | S-03 reconciliation variable inventory. |
| `S04-BREAKPOINT-VARIABLE-INVENTORY.md` | S-04 synthesis variable inventory. |
| `S05-BREAKPOINT-VARIABLE-INVENTORY.md` | S-05-owned variable inventory and first fixture ranking after the S-05 runtime split. |
| `S06-BREAKPOINT-VARIABLE-INVENTORY.md` | S-06 gap-handling variable inventory and S-05C consumer blocker. |
| `S07-BREAKPOINT-VARIABLE-INVENTORY.md` | S-07 finalization variable inventory and close-path reliability weakness signals. |
| `ENTERPRISE-SURVIVABILITY-SUITE.md` | End-to-end fail-closed diagnosability tier ladder, separate from stage breakpoint maturity. |
| `HARD-FAMILY-MEASUREMENT-FABRIC.md` | Adjacent measurement-fabric inventory for runner/API/discovery/bridge/Ghidra/artifact authority, separate from stage breakpoint maturity. |
| `HARD-FAMILY-MEASUREMENT-CONTROL-PLANE.md` | Traffic-light admission layer for hard-family lane and bridge scheduling, separate from stage breakpoint maturity. |
| `HARD-FAMILY-FAILURE-SIGNAL-MAP.md` | Canonical hard/full-suite failure-signal routing table from observed signal key to owner, row state, confidence, and next action. |
| `COMPILED-SUITE-GREEN-CONTRACT.md` | Green-label contract that separates compatibility, measurement, route, semantic, and product green for compiled suites. |
| `PIPELINE-PROVING-BASELINE-SNAPSHOTS.md` | Frozen proving posture before hard-family or expensive comparison runs. |

Future per-stage `PROVING-MAP.md` files are deferred until this central map
becomes too large to remain reviewable.

S-00, S-01, S-03, S-04, S-06, and S-07 inventory details live in the
corresponding `Sxx-BREAKPOINT-VARIABLE-INVENTORY.md` files. Those docs were
created by `s00_to_s07_pipeline_breakpoint_inventory_v1` as Tier 0 inventory surfaces.
They do not promote any row by themselves.

S-02 variable details live in
[`S02-BREAKPOINT-VARIABLE-INVENTORY.md`](S02-BREAKPOINT-VARIABLE-INVENTORY.md).
Rows stay at `planned/0` until real S-02 breakpoint fixtures exist. The current
S-02 exceptions are the S-02A ordering-quality Tier 2 anchor, the S-02B
raw-observation Tier 2 anchor, the S-02B argument-construction Tier 2 anchor,
the S-02B functional-precondition Tier 2 anchor, the S-02C probe-log durability
Tier 2 anchor, the S-02C finding-status persistence Tier 2 anchor, the
S-02A -> S-02B ordering-to-execution seam Tier 2 anchor, and the
S-02B -> S-02C raw-observation durability seam Tier 2 anchor, the
S-02C -> S-03 probe-evidence consumability seam Tier 2 anchor, and the first
S-02B -> S-02C -> S-03 bottom-up evidence-flow Tier 2 window. S-02 remains a
family-specific proving surface; these anchors do not claim all of S-02 is
Tier 2 or that every bottom-up S-02 composition window is proven.

S-05 variable details live in
[`S05-BREAKPOINT-VARIABLE-INVENTORY.md`](S05-BREAKPOINT-VARIABLE-INVENTORY.md).
Rows stay at `planned/0` until real S-05 breakpoint fixtures exist. The
current inventory records S-05A/B/C stage-owned families, S-05 seams, and S-05
bottom-up candidates. S-05 now has a row-classified full-family Tier 2
baseline: 17 rows are Tier 2, 5 rows are `blocked_at_tier2`, and 1 row is
`deferred_as_tier3_shaped`.

Enterprise survivability details live in
[`ENTERPRISE-SURVIVABILITY-SUITE.md`](ENTERPRISE-SURVIVABILITY-SUITE.md).
This is a separate proving axis: it measures whether hard-shaped runs finish
with comparable, non-comparable, warning, skipped, and final-packet boundaries.
It does not promote S-00 through S-07 breakpoint rows.
It also owns cross-cutting object-bound corrective authority, where a success
or audit token must be bound to the exact rejected, stale, unsafe, duplicate,
or quarantined object before product or survivability green can be claimed.

Hard-family failure signal routing lives in
[`HARD-FAMILY-FAILURE-SIGNAL-MAP.md`](HARD-FAMILY-FAILURE-SIGNAL-MAP.md).
Hard/full-suite observations must become canonical keys before they are used to
choose architecture work.

Hard-family measurement-fabric rows live in
[`HARD-FAMILY-MEASUREMENT-FABRIC.md`](HARD-FAMILY-MEASUREMENT-FABRIC.md).
This is an adjacent proving axis for the measurement network that creates hard
run evidence. It is not an S-00 through S-07 stage family, and it cannot
promote stage breakpoint rows.

Hard-family measurement control-plane rules live in
[`HARD-FAMILY-MEASUREMENT-CONTROL-PLANE.md`](HARD-FAMILY-MEASUREMENT-CONTROL-PLANE.md).
This is the traffic-light admission layer for runner/API/bridge scheduling. It
decides whether a target is green, yellow, red, or quarantined before analyzer
work starts; it cannot prove semantic target behavior.

Compiled-suite green language lives in
[`COMPILED-SUITE-GREEN-CONTRACT.md`](COMPILED-SUITE-GREEN-CONTRACT.md).
`Medium01` or hard-family green is not product green unless the run proves the
required route authority. For compiled enterprise product claims, that means
Ghidra-backed discovery plus decision-bearing semantic/product evidence.

Mutable product proving posture lives in
`configs/regression/product_proving_posture.json`. This map may summarize
operator posture, but the registry and posture files own active baselines,
local proving anchor, active pressure target, active blocker signal, and the
required external CI check name.

## Proving Dashboard

This dashboard is an operator and GM scan surface. The detailed rows below
remain authoritative for claim ceilings.

| Category | Count | Current state | Next gap |
| --- | ---: | --- | --- |
| Stage-owned breakpoint families | 67 | 32 are Tier 2, 1 is Tier 1, 2 are `failed_tier2`, 10 are `blocked_at_tier2`, 21 are `deferred_as_tier3_shaped` or planned lower maturity, and 1 is coordinator-adjacent planned/unimplemented | hard01 comparison should first check failed/blocked rows before contradicting Tier 2 claims |
| Seam-owned rows | 18 | 12 are Tier 2, 1 is Tier 1, 3 are `blocked_at_tier2`, and 2 remain planned lower maturity | add explicit S-05C decision consumer surface for S-06 and first S-03 -> S-04 / S-06 -> S-07 seams |
| Coordinator rows | 1 | `planned_unimplemented`; no implemented coordinator exists | post-S-00 coordinator only after seam pressure proves the need |
| Bottom-up window candidates | 11 | 3 are Tier 2, 3 are `blocked_at_tier2`, and 5 remain planned lower maturity | unblock S-05C -> S-06 and S-03 -> S-04 before broader bottom-up claims |
| Enterprise survivability suites | 9 families + 1 analyzer authority row | Tier 3 runner-equivalent compiled fixture ladder exists; bounded hard01 behavior now makes `session_bootstrap` comparable and object-bound corrective authority is mapped from live Hard01 branch-invalidation evidence; historical `reservation_stage` analyzer authority remains a measurement dependency | repair object-bound corrective authority before claiming hard-family semantic survivability, and keep measurement-fabric blockers separate when they recur |
| Hard-family measurement fabric | 10 families | Tier 0 inventory exists; lane identity, dependency blocking, signal routing, bridge-health admission, Tier 2 enforcement, Tier 3 selected routing, Tier 4 quarantine, Tier 5 hard01 readiness, and Ghidra-first route authority are covered guards or readiness gates; latest proof reached bridge authority and stopped at `bridge_stream_no_heartbeat` | route to bridge/Ghidra runtime authority; do not interpret hard01 semantics yet |
| Hard-family measurement control plane | 1 admission layer | Tier 5 hard01 readiness gate implemented after Tier 4 configured quarantine/recovery selection; `control_plane_green_but_bridge_stalled` remains a covered historical signal; bounded baseline attempts consumed readiness successfully: green target comparable, yellow target non-comparable, downstream dependency-blocked | keep control-plane gates intact while the next campaign inspects bridge/Ghidra runtime authority |
| Product baseline gate | registry-derived | Active defended product baselines are defined by `configs/regression/baseline_registry.json`; product gate membership and required fields are defined by `configs/regression/gate_v1.json`; local anchor and active pressure target are defined by `configs/regression/product_proving_posture.json`. | keep prose dashboards subordinate to registry/posture truth |
| Full-suite baselines | registry-derived | Fast, Required, and product baselines confirm composition under their stated contracts; they do not promote local stage rows unless attribution is local. | use as confirmation after local breakpoint movement and route/product proof |

Historical hard-family measurement-fabric snapshots remain routable: bounded
hard01 behavior now makes `session_bootstrap` comparable, and one prior route
was `analyzer_timeout` / `post_progress_10_control_stall`. Latest-proof-wins has
since moved the active key to `bridge_stream_no_heartbeat`.

`pipeline_full_tier2_baseline_v1` is the current full-pipeline row-classified
baseline. It preserves failed and blocked Tier 2 attempts as baseline data; a
green aggregate baseline suite does not mean every row is Tier 2.

S-07 close-path no-close weakness observed remains a live baseline signal,
now classified as `failed_tier2` for close-path reliability.

Pipeline-wide inventory sources:

| Stage family | Detail source | Current posture |
| --- | --- | --- |
| `S-00A/B/C` | `S00-BREAKPOINT-VARIABLE-INVENTORY.md` | one Tier 2 anchor per S-00 runtime stage; internal seams and bottom-up windows mostly planned |
| `S-01` | `S01-BREAKPOINT-VARIABLE-INVENTORY.md` | two local unlock rows now Tier 2; overtrust and bad-unlock rows are Tier 3-shaped |
| `S-02A/B/C` | `S02-BREAKPOINT-VARIABLE-INVENTORY.md` | strong partial Tier 2 baseline with known blocked rows |
| `S-03` | `S03-BREAKPOINT-VARIABLE-INVENTORY.md` | missing-observation local baseline is Tier 2; contradiction is failed_tier2; repeated unresolved is blocked_at_tier2 |
| `S-04` | `S04-BREAKPOINT-VARIABLE-INVENTORY.md` | evidence-grounded, missing-evidence, and uncertainty rows are Tier 2; contradiction docs remain blocked |
| `S-05A/B/C` | `S05-BREAKPOINT-VARIABLE-INVENTORY.md` | full-family baseline: 17 Tier 2, 5 blocked_at_tier2, 1 deferred_as_tier3_shaped |
| `S-06` | `S06-BREAKPOINT-VARIABLE-INVENTORY.md` | local gap-family and S-05C caveat rows are blocked_at_tier2; architecture-gap classification is Tier 3-shaped |
| `S-07` | `S07-BREAKPOINT-VARIABLE-INVENTORY.md` | close-path reliability is failed_tier2; other finalization rows remain blocked_at_tier2 pending focused harnesses |

Current S-02 Tier 2 anchors:

| Scope | Ownership | Breakpoint family |
| --- | --- | --- |
| `S-02A probe_ordering` | `stage-owned` | ordering quality |
| `S-02A probe_ordering` | `stage-owned` | prerequisite DAG honesty |
| `S-02A probe_ordering` | `stage-owned` | pass-scope containment |
| `S-02B invocation_execution` | `stage-owned` | raw observation integrity |
| `S-02B invocation_execution` | `stage-owned` | argument construction |
| `S-02B invocation_execution` | `stage-owned` | functional precondition handling |
| `S-02C evidence_capture` | `stage-owned` | probe-log durability |
| `S-02C evidence_capture` | `stage-owned` | finding-status persistence |
| `S-02C evidence_capture` | `stage-owned` | state-effect preservation |
| `S-02C evidence_capture` | `stage-owned` | post-probe recalibration honesty |
| `S-01 -> S-02A` | `seam-owned` | unlock-to-ordering handoff |
| `S-02A -> S-02B` | `seam-owned` | ordering-to-execution preservation |
| `S-02B -> S-02C` | `seam-owned` | raw-observation durability |
| `S-02C -> S-03` | `seam-owned` | probe evidence consumability |
| `S-02C -> S-03` | `seam-owned` | missing-observation deferral |
| `S-02B -> S-02C -> S-03` | `bottom-up window` | raw runtime evidence becomes reconciliation input |

Current S-02 `blocked_at_tier2` rows:

| Scope | Ownership | Breakpoint family | Blocker |
| --- | --- | --- | --- |
| `S-02B invocation_execution` | `stage-owned` | lane/runtime failure classification | no deterministic lane-failure harness yet separates infrastructure failure from compiled product-call failure |
| `S-02B invocation_execution` | `stage-owned` | overtrust prevention | meaningful proof is Tier 3-shaped without a hard ambiguity fixture; a shallow Tier 2 would be theater |
| `S-02A -> S-02B -> S-02C` | `bottom-up window` | ordered work becomes durable evidence | current execution duplicates the read target and drops the write target under ordered S-02A scope |

Current S-02 bottom-up composition:

| Window | State | Why deferred |
| --- | --- | --- |
| `S-01 -> S-02A -> S-02B` | `planned/0` | unlock-to-ordering seam is anchored, but this bottom-up window has not been built |
| `S-02A -> S-02B -> S-02C` | `blocked_at_tier2` | attempted ordered evidence window found duplicate read execution and dropped write execution under ordered S-02A scope |
| `S-02B -> S-02C -> S-03` | `Tier 2` | first bottom-up evidence-flow window is green; missing-observation deferral and S-03 contradiction maturity remain separate |

Current S-05 inventory snapshot:

| Category | Count | Current state | Next gap |
| --- | ---: | --- | --- |
| Stage-owned breakpoint families | 16 | 12 are `Tier 2`, 3 are `blocked_at_tier2`, 1 is `deferred_as_tier3_shaped` | fix state-effect replay harness, retry containment widening, or bridge/degradation harness |
| Seam-owned breakpoint families | 4 | 3 are `Tier 2`, 1 is `blocked_at_tier2` | add explicit S-05C decision consumer surface for S-06 |
| Bottom-up window candidates | 3 | 2 are `Tier 2`, 1 is `blocked_at_tier2` | unblock S-05C -> S-06 before claiming the last window |
| Total S-05 proving families/windows | 23 | 17 are `Tier 2`, 5 are `blocked_at_tier2`, 1 is `deferred_as_tier3_shaped` | use this as the S-05 hard01 prediction surface |

## Breakpoint Suite Rule

Breakpoint suites are stage-first, not fixture-first. A breakpoint family must
come from the owner obligation and the independent variables that could break
that obligation.

A seam suite such as `S-00C -> S-01` must still name:

- producer stage
- consumer stage
- blocker family
- expected producer artifact
- expected handoff or admission behavior
- expected consumer behavior
- legal fallback behavior
- owner if observed behavior differs

Add one named breakpoint family at a time. Do not start with a broad harder
suite when a narrow fixture can expose the expected versus observed behavior.
Each breakpoint suite should include a pressure-pattern case, or explicitly
record why pressure remains deferred. Pressure cases should prefer compiled
DLL fixtures when the behavior depends on real binary/static-analysis surfaces;
Python-only tests are support checks, not replacements for product-shaped
evidence.

## First Breakpoint Ranking

Use this score when choosing the next breakpoint suite. Higher is more urgent.

| Criterion | Meaning |
| --- | --- |
| `diagnostic_value` | Failure points to a clear owner rather than the whole pipeline. |
| `migration_relevance` | The suite pressures the active stage-split or stage-strengthening frontier. |
| `existing_gap` | Existing Easy/Medium/Hard gates are likely to miss this behavior. |
| `fixture_cost` | Lower-cost fixtures score higher because they enable faster iteration. |
| `downstream_value` | Passing the suite makes later stages clearer, narrower, or easier to diagnose. |

If a second opinion is needed, ask the reviewer or subagent to score each
candidate from `1` to `10` on those criteria and provide one paragraph for the
highest disagreement. The GM keeps final branch choice.

Current top-ranked candidate:

| Candidate | diagnostic_value | migration_relevance | existing_gap | fixture_cost | downstream_value | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `S-00/S-01 admitted target and fallback behavior` | 9 | 10 | 8 | 9 | 9 | Built first as the seam-owned Tier 1 anchor. |
| Pure S-00 static inventory richness | 7 | 8 | 8 | 7 | 6 | Defer until runtime-visible S-00A/B/C split clarifies owner. |
| Broad harder end-to-end fixture | 5 | 6 | 6 | 3 | 7 | Keep as upper-ladder confirmation, not first diagnostic. |

## Central Scorecard

Skeleton rows are intentionally provisional. `planned/0` means no real
breakpoint fixture exists yet. Do not treat it as coverage.

| Scope | ownership_type | Semantic obligation | Systems in play | Emitted artifacts or handoff | Likely breakpoint families | Current tier | Target tier | Claim ceiling | Missing fixtures |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `S-00A setup_baseline` | `stage-owned` | Establish sentinel and vocab baseline before static evidence. | Sentinel calibration, prior context, vocab seeding. | `sentinel_calibration.json`, `vocab.json`, setup checkpoint status. | Sentinel/vocab thinness; missing static strings; prior-context overtrust. | `Tier 2` | `Tier 3` | Setup baseline handles noisier prior hints and multiple explicit sentinels in deterministic medium compiled-context pressure. | Tier 3 ambiguous/static-thin setup fixture with conflicting hints and deterministic expected fallback. |
| `S-00B static_evidence` | `stage-owned` | Produce bounded static evidence and normalized enrichment without claiming runtime truth. | Static scanner, callable inventory, string extraction, static enrichment. | `static_analysis.json`, `static_enrichment.json`, optional `call_graph.json`, optional `ghidra_data_types.json`. | Callable inventory richness; static string thinness; enrichment provenance; raw-overread prevention. | `Tier 2` | `Tier 3` | Static evidence handles medium compiled callable pressure, capped inventory, richer strings, and absent-Ghidra ambiguity. | Tier 3 ambiguous/static-thin fixture with conflicting names, weak strings, and deterministic provenance expectations. |
| `S-00C admission_handoff` | `stage-owned` | Convert setup/static evidence into admitted, deferred, ambiguous, and target surfaces for S-01. | Handoff packet builder, admission capping, target selection, ambiguity register. | `s01_handoff_packet.json`, `coordination_decision`, `s01_targets`, `ambiguity_register`. | Admission capping; deferred evidence honesty; weak-target non-overtrust; cross-DLL hint deferral. | `Tier 2` | `Tier 3` | Admission handoff preserves bounded target admission and reviewable deferred static evidence under medium compiled pressure. | Tier 3 admission fixture with static-thin/conflicting hints and deterministic non-overtrust expectations. |
| `S-00C -> S-01` | `seam-owned` | Prove admitted packet targets affect bounded S-01 work while fallback remains intact. | S-00C packet output, shared handoff contract, S-01 target prioritization. | Producer packet plus consumer probe ordering. | `admission pressure`; fallback preservation; target capping; malformed/thin packet handling. | `Tier 1` | `Tier 3` | `handoff survives one easy compiled pressure case` | Tier 2 medium-pressure fixture; Tier 3 ambiguous/static-thin fixture. |
| `S-01 unlock` | `stage-owned` | Use admitted setup guidance to prioritize bounded unlock probing while preserving fallback. | Unlock candidate selection, probe ordering, write/init target handling. | `write_unlock_probe.json`, unlock result fields, S-01 consumer use of `s01_targets`. | Unlock target prioritization; fallback under weak guidance; overtrust prevention; candidate exhaustion. | `Tier 0 support + seam Tier 1` | `Tier 3` | S-01 has seam participation evidence, not an unlock-owned ladder. | Unlock-owned compiled fixture; probe-order pressure fixture. |
| `S-01 -> S-02A` | `seam-owned` | Preserve unlock evidence into probe ordering without losing failure attribution. | Unlock outputs, probe admission, ordering metadata. | Unlock results handed to S-02A ordering inputs. | Unlocked target handoff; bad unlock containment; ordering fallback. | `Tier 2` | `Tier 3` | Unlock evidence can guide S-02A ordering under medium compiled pressure without dropping fallback candidates or claiming unlock truth. | Tier 3 malformed/bad-unlock containment remains unproven. |
| `S-02A probe_ordering` | `stage-owned` | Order invocables and preserve prerequisite-state planning without executing calls. | Curriculum ordering, prerequisite DAG, pass-scope planning. | `prerequisite_state_machine.json`, `s02_probe_ordering` checkpoint/status. | Ordering quality; prerequisite DAG honesty; pass-scope containment; repeated-probe classification. | `Tier 2` | `Tier 3` | S-02A has Tier 2 anchors for ordering quality, prerequisite DAG honesty, and pass-scope containment; repeated-probe classification remains separate. | Tier 3 hard ordering/repeated-probe pressure remains unproven. |
| `S-02A -> S-02B` | `seam-owned` | Preserve ordered probe work into execution without overtrusting prerequisite plans. | Ordered queue, prerequisite state, execution input metadata. | Ordered invocables and prerequisite-state context handed to S-02B. | Ordering-to-execution loss; prerequisite overtrust; pass-scope leakage. | `Tier 2` | `Tier 3` | S-02B receives the S-02A ordered plan and preserves execution order under medium compiled seam pressure. | Tier 3 hard seam fixture; prerequisite overtrust remains a separate variable. |
| `S-02B invocation_execution` | `stage-owned` | Construct arguments, execute calls, and observe raw runtime behavior. | Lane execution, bridge metadata, argument construction, raw call results. | Probe log entries, model context, user-message sample, execution observations. | Argument construction; overtrust prevention; lane/runtime failure classification; functional precondition handling; raw observation integrity. | `Tier 2 + blocked_at_tier2` | `Tier 3` | S-02B has Tier 2 anchors for raw observation integrity, argument construction, and functional precondition handling; lane/runtime failure classification and overtrust prevention are blocked below Tier 2. | Deterministic lane-failure harness; Tier 3 overtrust/ambiguity fixture. |
| `S-02B -> S-02C` | `seam-owned` | Preserve raw observations into durable evidence capture. | Probe log stream, raw findings, checkpoint update input. | Raw observations handed to evidence capture/persistence. | Raw-observation durability; persistence mismatch; dropped state effects. | `Tier 2` | `Tier 3` | S-02B raw observations survive the live S-02C durability handoff under medium compiled pressure. | Tier 3 hard durability seam pressure; persistence mismatch remains separate. |
| `S-02C evidence_capture` | `stage-owned` | Persist probe evidence, update findings/checkpoints, and run post-probe recalibration. | Probe log durability, finding persistence, checkpoint writes, sentinel recalibration. | `explore_probe_log.json`, `evidence/stage-02c-evidence-capture/probe-log.json`, `evidence/stage-02c-evidence-capture/finding-status.json`, `findings.json`, `s02_evidence_capture` checkpoint/status. | Probe-log durability; finding status persistence; state-effect preservation; downstream consumability; post-probe recalibration honesty. | `Tier 2` | `Tier 3` | S-02C has Tier 2 anchors for probe-log durability, finding-status persistence, state-effect preservation, and additive recalibration honesty. | Tier 3 hard durability/status/state pressure remains unproven. |
| `S-02C -> S-03` | `seam-owned` | Preserve probe evidence so reconciliation can classify contradictions. | Probe evidence schema, finding ingestion, contradiction input surface. | Probe results handed to reconciler. | Probe evidence consumability; missing-observation deferral; contradictory probe packet handling. | `Tier 2` | `Tier 3` | S-03 consumes S-02C durable probe evidence and defers missing/blocked observations under medium focused seam pressure. | Contradictory packet handling and S-03 local contradiction maturity remain separate. |
| `S-03 reconcile` | `stage-owned` | Reconcile contradictions against evidence and classify unresolved write failures. | Contradiction rules, evidence ranking, blocker attribution. | Reconciled findings and contradiction status. | Contradictory evidence; repeated unresolved status; false repair; wrong blocker attribution. | `mixed: Tier 2, failed_tier2, blocked_at_tier2, deferred_as_tier3_shaped` | `Tier 3` | Missing-observation deferral has focused Tier 2 evidence; contradiction classification failed Tier 2; repeated unresolved lacks explicit local surface. | Add local contradiction and unresolved-status surfaces before Tier 3. |
| `S-03 -> S-04` | `seam-owned` | Preserve reconciled evidence so synthesis does not invent confidence. | Reconciled finding schema, evidence confidence, synthesis input contract. | Reconciled findings handed to synthesis. | Low-confidence claim transfer; contradiction visibility; missing evidence handoff. | `blocked_at_tier2` | `Tier 2` | No seam claim; blocked until S-03 uncertainty reaches S-04 through an explicit handoff harness. | Reconcile-to-synthesis fixture. |
| `S-04 synthesis` | `stage-owned` | Produce readable API documentation from evidence without claiming verification. | Documentation synthesis, evidence citation, uncertainty preservation. | API reference or synthesis artifacts. | Missing-evidence synthesis honesty; overconfident docs; uncertainty omission. | `mixed: Tier 2, blocked_at_tier2, deferred_as_tier3_shaped` | `Tier 3` | Evidence-grounded synthesis, missing-evidence honesty, and uncertainty preservation have focused Tier 2 harness evidence; contradiction visibility remains blocked. | Contradiction-visibility fixture, then Tier 3 overconfidence fixture. |
| `S-05 enrichment` | `stage-owned compatibility parent` | Preserve legacy S-05 checkpoint and artifact compatibility while S-05A/B/C own runtime attribution. | Parent checkpoint, legacy artifacts, runner compatibility. | `s05_enrichment` checkpoint/status and legacy artifact paths. | Parent/child compatibility drift; legacy path removal risk. | `runtime split` | `not a breakpoint target` | S-05 parent compatibility remains; stage-owned maturity belongs to S-05A/B/C. | No breakpoint fixture should target the parent as a substitute for child stages. |
| `S-04 -> S-05A` | `seam-owned` | Preserve synthesized claims into schema backfill without treating prose as proof. | Synthesis output, schema backfill input, claim provenance. | Synthesized claims handed to S-05A. | Prose-as-proof leakage; schema mismatch; weak-provenance handoff. | `Tier 2` | `Tier 3` | S-05A consumes S-04-shaped synthesis with provenance and uncertainty intact. | Tier 3 mixed synthesis pressure. |
| `S-05A schema_backfill` | `stage-owned` | Backfill schema descriptions from synthesis without claiming verification truth. | Schema backfill, synthesis-derived descriptions, schema snapshots. | `backfill_result.json`, `mcp_schema_post_discovery.json`, `s05_schema_backfill` checkpoint/status. | Schema provenance; prose-as-proof prevention; partial-backfill honesty; schema compatibility preservation. | `Tier 2 for all four known S-05A families` | `Tier 3` | S-05A records provenance and preserves prose, partial-backfill, and compatibility boundaries under medium schema pressure. | Tier 3 mixed-provenance ambiguity. |
| `S-05A -> S-05B` | `seam-owned` | Preserve schema backfill outputs into verification without promoting enrichment to proof. | Backfill result, schema snapshot, verification inputs. | Backfilled schema and findings handed to S-05B. | Enrichment-as-proof leakage; schema drift; weak backfill overtrust. | `Tier 2` | `Tier 3` | S-05B keeps enriched schema separate from replay evidence under medium seam pressure. | Tier 3 enrichment/replay ambiguity. |
| `S-05B verification_replay` | `stage-owned` | Re-execute and classify working-call/state-effect evidence without promoting weak positives. | Direct replay, stateful verification, bridge degradation handling, finding patching. | `verification-report.json`, patched findings, `s05_verification_replay` checkpoint/status. | Direct replay truth; state-effect verification; weak-positive non-promotion; bridge/degradation classification; finding-patch honesty; partial verification coverage. | `Tier 2 for direct replay, weak-positive, finding-patch, and partial coverage; blocked_at_tier2 for state-effect and bridge/degradation` | `Tier 3` | S-05B replay and patch boundaries are stronger, but state effects and infra-vs-product failure ownership remain blocked. | Build deterministic same-session state-effect and bridge/degradation harnesses. |
| `S-05B -> S-05C` | `seam-owned` | Preserve verified read evidence into bounded read-to-write chaining. | Verification report, findings, MC-5 input selection. | Verified read evidence handed to MC-5 chaining. | Verified/unverified confusion; read-output extraction loss; weak-ID overtrust. | `Tier 2 for verified-to-chaining boundary only` | `Tier 3` | S-05C chains only from S-05B-verified read evidence under medium seam pressure; this does not prove S-05 bottom-up maturity, S-05C retry execution correctness, S-05C -> S-06 gap handoff, or MC-5 end-to-end success. | Next S-05A -> S-05B seam or S-05C -> S-06 seam fixture. |
| `S-05C read_to_write_chaining` | `stage-owned` | Use verified read outputs for bounded MC-5 write retry decisions. | MC-5 coordinator, value extraction, retry plan containment. | `mc-decisions/mc5-post-verification.json`, `s05_read_to_write_chaining` checkpoint/status. | Verified-read extraction; read-to-write dependency honesty; retry containment; weak-ID/value overtrust; MC-5 decision durability; unresolved deferral. | `Tier 2 for verified-read extraction, dependency honesty, MC-5 durability, unresolved deferral; blocked_at_tier2 for retry containment; weak-ID/value overtrust deferred_as_tier3_shaped` | `Tier 3` | S-05C selection and decision durability are stronger, but retry containment still widens to distractor writes and weak-ID/value overtrust is hard-pressure shaped. | Fix containment before broad S-05C maturity claims. |
| `S-05C -> S-06` | `seam-owned` | Preserve unresolved and caveated retry outcomes into gap handling. | MC-5 decisions, verification report, gap input register. | Unresolved targets and caveats handed to S-06. | Caveat loss; unresolved-item widening; verified/unverified confusion. | `blocked_at_tier2` | `Tier 2` | No Tier 2 claim; S-06 lacks an explicit S-05C decision-consumer surface. | Add S-05C decision consumer boundary in S-06. |
| `S-06 gaps` | `stage-owned` | Retry or surface unresolved gaps and clarification questions. | Gap register, retry selection, clarification generation, S-05C caveat consumption. | Gap register and clarification questions. | Repeated gap family; retry exhaustion; irrelevant clarification; architecture-gap classification; unresolved S-05C caveat consumption. | `blocked_at_tier2 with Tier 3-shaped architecture-gap row` | `Tier 3` | Repeated gap-family, retry exhaustion, clarification relevance, and S-05C caveat consumption are blocked by missing explicit local/consumer surfaces. | Add S-05C decision consumer boundary, then repeated-gap and retry-exhaustion fixtures. |
| `S-06 -> S-07` | `seam-owned` | Preserve knowns, unknowns, and trust boundaries for finalization. | Gap outputs, finalization input, trust-boundary transfer. | Known/unknown packet handed to S-07. | Trust-boundary loss; unresolved uncertainty hiding; finalization input mismatch. | `blocked_at_tier2` | `Tier 2` | Blocked until S-06 trust-boundary output is local and reviewable. | Gaps-to-finalize fixture. |
| `S-07 finalize` | `stage-owned` | Close with knowns, unknowns, trust boundaries, and final reviewable artifacts. | Final report, artifact/session packaging, checkpoint terminalization. | Final report, session artifacts, terminal status, checkpoint summaries. | Final-output trust boundary; unresolved uncertainty visibility; artifact/session packaging durability; close-path reliability; terminal status correctness. | `failed_tier2 for close-path reliability; other rows blocked_at_tier2` | `Tier 2` | Medium01 exposed `s07_finalize_vocab_persist_no_close` and `s07_macro_verdict_persist_no_close`; focused Tier 2 close-path attempt preserves no-close as baseline failure. | Close-path reliability fix campaign, then trust-boundary and packaging fixtures. |
| `post-S-00 coordinator` | `coordinator-owned` | Future coordinator narrows, groups, defers, or escalates rich S-00 packets before S-01. | Planned coordinator/admission logic, packet narrowing, risk classification. | Future coordinator packet or narrowed admission slice. | Packet narrowing under pressure; over-deferral; over-admission; escalation correctness. | `planned_unimplemented` | `Tier 3` | No coordinator claim because the coordinator is not implemented. | Coordinator pressure fixture after the coordinator exists. |

## First Suite Contract

Suite: `s00_s01_breakpoint_suite`

Ownership type: `seam-owned`

Breakpoint family: `admission pressure`

Current tier: `Tier 1`

Target tier: `Tier 3`

Claim ceiling: `handoff survives one easy compiled pressure case`

Benchmark question:

Can the `S-00C -> S-01` seam use admitted packet targets to change bounded
S-01 work ordering while preserving fallback and admission honesty?

Questions this suite can answer:

- whether strong admitted `init_candidates` and `write_candidates` are consumed
  before probing
- whether malformed, missing, thin, or unmatched targets keep legacy fallback
- whether broad target sets stay capped and reviewable
- whether S-00 producer, shared handoff, and S-01 consumer ownership remain
  attributable

Questions this suite cannot answer:

- whether the full product unlocks a real hard-family DLL
- whether GhidraMCP evidence is complete
- whether S-00A, S-00B, or S-00C is individually Tier 1+
- whether S-02 through S-07 semantics are correct
- whether cross-DLL dependency handling is solved

What the next suite in this category should add:

- Tier 2 medium-pressure compiled fixture with noisier names, more distractors,
  and richer but deterministic static hints
- Tier 3 ambiguous/static-thin fixture that forces honest deferral and
  overtrust prevention
- bottom-up `S-00B -> S-00C -> S-01` integration window when S-00B and S-00C
  have stage-owned anchors

## S-00 Stage-Owned Tier 1 And Tier 2 Anchors

Suite: `s00_substage_breakpoint_suite`

Questions this suite can answer:

- whether `S-00A setup_baseline` preserves hinted vocab and sentinel evidence
  without inventing static evidence
- whether `S-00B static_evidence` extracts callable and string inventory from
  one easy compiled pressure fixture while recording missing Ghidra ambiguity
- whether `S-00C admission_handoff` caps broad target guidance and keeps
  deferred or ambiguous static material reviewable before S-01 consumption
- whether `S-00A setup_baseline` handles noisier prior hints and multiple
  explicit sentinels in a deterministic medium compiled-context case
- whether `S-00B static_evidence` handles medium compiled callable pressure,
  richer strings, and callable inventory caps while preserving absent-Ghidra
  ambiguity
- whether `S-00C admission_handoff` preserves bounded target admission and
  reviewable deferred static evidence under medium compiled pressure

Questions this suite cannot answer:

- whether S-00A/B/C are Tier 3
- whether the post-S-00 coordinator is needed or correct
- whether S-01 consumes the packet correctly under medium or hard pressure
- whether Easy01, Medium01, or hard-family product behavior is non-regressed

What the next suite in this category should add:

- Tier 3 ambiguous/static-thin/conflicting-hint pressure for one S-00 substage
  at a time
- deterministic non-overtrust and fallback expectations before any Tier 3
  promotion
- coordinator-owned pressure only if S-00C remains honest but seam judgment
  becomes the actual blocker

## S-02A Stage-Owned Tier 2 Anchor

Suite: `s02a_probe_ordering_breakpoint_suite`

Ownership type: `stage-owned`

Breakpoint family: `ordering quality`

Current tier: `Tier 2`

Target tier: `Tier 3`

Claim ceiling: `S-02A can produce a useful ordered probe plan under medium naming pressure`

Benchmark question:

Can `S-02A probe_ordering` take medium-pressure compiled callable inventory and
produce a useful ordered probe plan without dropping candidates, duplicating
candidates, or executing calls?

Questions this suite can answer:

- whether S-02A emits start/done status for the probe-ordering boundary
- whether S-02A preserves all candidate invocables while reordering them
- whether setup/init and read-like producers move ahead of write/commit-like
  consumers under medium naming pressure
- whether `prerequisite_state_machine.json` remains reviewable for the ordered
  plan

Questions this suite cannot answer:

- whether the prerequisite DAG is semantically true
- whether S-02B executes the ordered plan correctly
- whether S-02C persists execution evidence durably
- whether S-01 unlock guidance quality is correct
- whether Easy01, Medium01, or hard-family behavior is non-regressed

What the next suite in this category should add:

- S-02B argument construction Tier 2, because bad arguments can still poison
  execution even after S-02A produces a useful order
- a separate S-02A prerequisite DAG honesty fixture before claiming broader
  probe-ordering maturity
- Tier 3 ambiguous or hard ordering pressure only after deterministic expected
  behavior is defined

## S-02B Stage-Owned Tier 1 And Tier 2 Anchors

Suite: `s02b_invocation_execution_breakpoint_suite`

Ownership type: `stage-owned`

Breakpoint family: `raw observation integrity`

Current tier: `Tier 2`

Target tier: `Tier 3`

Claim ceiling: `S-02B preserves raw observations under medium compiled invocation pressure`

Benchmark question:

Can `S-02B invocation_execution` execute easy and medium-pressure compiled DLL
functions through the current deterministic probe-loop seam and preserve raw
function name, arguments, result text, backend trace, typed argument values,
classification boundary, and substage status without semantic rewriting?

Questions this suite can answer:

- whether S-02B emits start/done status for the invocation-execution boundary
- whether S-02B preserves function name and arguments for easy compiled calls
- whether raw result text and backend trace survive into the probe log
- whether a real compiled DLL path can support narrow S-02B breakpoint checks
- whether medium compiled pressure with multiple deterministic raw statuses and
  one typed integer argument preserves raw facts without rewriting

Questions this suite cannot answer:

- whether S-02B has Tier 3 hard raw-observation maturity
- whether lane/runtime failures are classified correctly
- whether S-02C persists the observation durably
- whether S-03 interprets the observation correctly
- whether Easy01, Medium01, or hard-family behavior is non-regressed

What the next suite in this category should add:

- the active `s02_tier2_grounding_priority_v1` sequence has added S-02A
  ordering quality and S-02B argument construction Tier 2 anchors; the next
  priority is S-02B functional precondition handling, followed by S-02C
  finding-status persistence and the S-02A -> S-02B ordering-to-execution seam
- Tier 3 hard raw-observation pressure with deterministic ambiguous statuses,
  repeated observations, or harder but single-family raw preservation
  expectations
- a separate deterministic lane/runtime failure-classification fixture before
  any Tier 3 claim

## S-02B Argument Construction Tier 2 Anchor

Suite: `s02b_argument_construction_breakpoint_suite`

Ownership type: `stage-owned`

Breakpoint family: `argument construction`

Current tier: `Tier 2`

Target tier: `Tier 3`

Claim ceiling: `S-02B constructs usable typed arguments for medium-pressure simple exports`

Benchmark question:

Can `S-02B invocation_execution` construct visible typed fallback arguments for
medium-pressure compiled DLL exports and route those arguments into the actual
compiled call path?

Questions this suite can answer:

- whether S-02B builds deterministic typed arguments for quantity, amount,
  mode, and combined integer parameters
- whether the compiled DLL receives those arguments, proven by encoded return
  values rather than only Python-side probe-log shape
- whether argument source metadata remains reviewable in the raw observation
  row

Questions this suite cannot answer:

- whether raw observation integrity is broadly mature beyond the separate
  raw-observation suite
- whether lane/runtime failures are classified correctly
- whether blocked functional preconditions are handled honestly
- whether S-02C persists the observation durably
- whether S-03 interprets the observation correctly

What the next suite in this category should add:

- S-02A -> S-02B ordering-to-execution seam pressure, because S-02C
  finding-status persistence now has a separate anchor
- Tier 3 argument-construction pressure only after deterministic hard fixture
  expectations exist

## S-02B Functional Precondition Handling Tier 2 Anchor

Suite: `s02b_functional_precondition_breakpoint_suite`

Ownership type: `stage-owned`

Breakpoint family: `functional precondition handling`

Current tier: `Tier 2`

Target tier: `Tier 3`

Claim ceiling: `S-02B records blocked calls without pretending final semantics are known`

Benchmark question:

Can `S-02B invocation_execution` preserve blocked-before-init and
allowed-after-init observations from a stateful compiled DLL without rewriting
the blocked call into final semantic truth?

Questions this suite can answer:

- whether S-02B records a write-like call blocked before init as a raw
  observation with not-initialized classification
- whether a later init call and write-like call after init are also preserved
  as raw observations
- whether function names, args, result text, backend trace, and classification
  boundaries remain reviewable

Questions this suite cannot answer:

- whether lane/runtime failures are classified correctly
- whether S-02A selected the best order
- whether S-02C persists the observation durably
- whether S-03 interprets preconditions correctly
- whether Tier 3 ambiguous or conflicting precondition pressure is handled

What the next suite in this category should add:

- S-02A -> S-02B ordering-to-execution seam pressure after S-02C status
  persistence is anchored
- Tier 3 precondition pressure only after deterministic hard fixture
  expectations exist

## S-02C Stage-Owned Tier 1 And Tier 2 Anchors

Suite: `s02c_evidence_capture_breakpoint_suite`

Ownership type: `stage-owned`

Breakpoint family: `probe-log durability`

Current tier: `Tier 2`

Target tier: `Tier 3`

Claim ceiling: `S-02C persists multiple raw observation packets under medium durability pressure without loss or semantic rewriting`

Benchmark question:

Can `S-02C evidence_capture` read one or multiple S-02B-shaped raw observation
packets and persist the S-02C-owned probe-log snapshot without losing row
order, function name, args, raw result text, trace/backend metadata, argument
count, or classification/status boundary?

Questions this suite can answer:

- whether S-02C emits start/done status for evidence capture
- whether S-02C creates its owned probe-log alias artifact
- whether one easy raw observation packet survives persistence without semantic
  rewriting
- whether multiple mixed raw observations preserve row order, typed args, raw
  results, trace metadata, and classification boundaries under medium pressure
- whether malformed legacy probe logs degrade safely without breaking the stage

Questions this suite cannot answer:

- whether S-02B execution is correct
- whether S-02C has Tier 3 hard durability maturity
- whether S-02C preserves finding status distinctions outside the probe-log
  snapshot
- whether S-03 reconciliation consumes the artifact correctly
- whether session ZIP capture or broad Easy01/Medium01 behavior is
  non-regressed

What the next suite in this category should add:

- Tier 3 hard durability pressure with ambiguous, repeated, or
  conflicting-looking observations and deterministic preservation expectations
- separate state-effect preservation and downstream-consumability anchors

## S-02C Finding-Status Persistence Tier 2 Anchor

Suite: `s02c_finding_status_persistence_breakpoint_suite`

Ownership type: `stage-owned`

Breakpoint family: `finding status persistence`

Current tier: `Tier 2`

Target tier: `Tier 3`

Claim ceiling: `S-02C preserves observed, blocked, ambiguous, and unresolved finding-status distinctions under medium pressure`

Benchmark question:

Can `S-02C evidence_capture` persist a status-focused snapshot that keeps
observed, blocked, ambiguous, and unresolved rows distinct without relying on
S-03 interpretation or bottom-up pipeline success?

Questions this suite can answer:

- whether S-02C creates its owned finding-status alias artifact
- whether observed, blocked, ambiguous, and unresolved distinctions are
  preserved under medium pressure
- whether status rows remain linked to function name, args, result excerpt,
  phase, trace metadata, and classification boundary

Questions this suite cannot answer:

- whether S-02B execution is correct
- whether S-02B and S-02C agree across a live seam
- whether S-03 consumes or interprets the status artifact correctly
- whether session ZIP capture or broad Easy01/Medium01 behavior is
  non-regressed

What the next suite in this category should add:

- Tier 3 S-02A -> S-02B ordering-to-execution seam pressure only after hard
  deterministic expectations exist
- Tier 3 hard status-distinction pressure with repeated or conflicting-looking
  status signals
- Tier 3 hard durability pressure with ambiguous, repeated, or
  conflicting-looking observations and deterministic preservation expectations

## S-02A -> S-02B Seam Tier 2 Anchor

Suite: `s02a_s02b_ordering_execution_seam_breakpoint_suite`

Ownership type: `seam-owned`

Breakpoint family: `ordering-to-execution preservation`

Current tier: `Tier 2`

Target tier: `Tier 3`

Claim ceiling: `S-02B receives the S-02A ordered plan and preserves execution order under medium compiled seam pressure`

Benchmark question:

Can `S-02B invocation_execution` consume the ordered invocable plan emitted by
`S-02A probe_ordering` rather than silently reverting to original scrambled
input order under medium compiled seam pressure?

Questions this suite can answer:

- whether S-02A emits an ordered plan from the medium compiled ordering fixture
- whether S-02B starts after that plan and processes direct deterministic
  fallback rows in S-02A order
- whether the seam keeps candidate identity intact without dropping or
  duplicating invocables
- whether prerequisite-state-machine upload remains reviewable for the seam

Questions this suite cannot answer:

- whether S-02A prerequisite DAG guidance is semantically true
- whether S-02B execution correctness is broadly mature
- whether S-02B handles prerequisite overtrust under hard pressure
- whether S-02C persists the resulting observations durably
- whether a bottom-up S-02A -> S-02B -> S-02C window is green

What the next suite in this category should add:

- Tier 3 hard seam pressure with ambiguous prerequisite-looking distractors and
  deterministic expected behavior
- S-02B lane/runtime failure classification only after a controlled failure
  harness exists
- the first bottom-up S-02A -> S-02B -> S-02C window only after seam and
  stage-owned anchors stay green

## S-02B -> S-02C Seam Tier 2 Anchor

Suite: `s02b_s02c_raw_observation_durability_seam_breakpoint_suite`

Ownership type: `seam-owned`

Breakpoint family: `raw-observation durability`

Current tier: `Tier 2`

Target tier: `Tier 3`

Claim ceiling:

`S-02B raw observations survive the live S-02C durability handoff under medium
compiled pressure`.

Benchmark question:

Can raw observations emitted by S-02B from the medium compiled DLL fixture pass
through the legacy probe-log handoff and arrive in S-02C-owned durable aliases
without losing order, function names, args, result excerpts, backend traces,
raw results, argument counts, or classification/status boundaries?

Questions this suite can answer:

- whether S-02B append rows are readable by S-02C through the live seam shape
- whether S-02C aliases preserve S-02B raw observation fields exactly
- whether status snapshots preserve the existing classification boundary

Questions this suite cannot answer:

- whether S-02C -> S-03 reconciliation can consume the resulting evidence
- whether lane/runtime failure classification is correct
- whether S-02A -> S-02B -> S-02C is green as a bottom-up window
- whether all S-02 evidence capture variables are Tier 2

What the next suite in this category should add:

- S-02C -> S-03 probe-evidence consumability after this seam stays green
- first S-02A -> S-02B -> S-02C bottom-up window only after adjacent seams are
  anchored
- Tier 3 hard seam pressure only after deterministic ambiguous/repeated
  handoff expectations exist

## S-02C -> S-03 Seam Tier 2 Anchor

Suite: `s02c_s03_probe_evidence_consumability_breakpoint_suite`

Ownership type: `seam-owned`

Breakpoint family: `probe evidence consumability`

Current tier: `Tier 2`

Target tier: `Tier 3`

Claim ceiling:

`S-03 consumes S-02C durable probe evidence boundaries under medium focused
seam pressure`.

Claim ceiling summary: S-03 consumes S-02C durable probe evidence boundaries under medium focused seam pressure.

Benchmark question:

Can S-03 reconciliation prefer the S-02C-owned durable probe-log alias, fall
back to legacy probe logs when the alias is absent, and patch only findings
whose raw S-02C evidence justifies reconciliation?

Questions this suite can answer:

- whether S-03 reads `evidence/stage-02c-evidence-capture/probe-log.json`
  before legacy `explore_probe_log.json`
- whether a success-like S-02C probe row can repair an error finding
- whether blocked or missing observations avoid false success
- whether legacy probe-log fallback remains compatible

Questions this suite cannot answer:

- whether S-02B -> S-02C -> S-03 is green as a bottom-up window
- whether S-03 contradiction maturity is Tier 2 or Tier 3
- whether MC-3 write analysis is correct
- whether missing-observation deferral has its own seam anchor

What the next suite in this category should add:

- `S-02C -> S-03` missing-observation deferral if absence handling becomes the
  next blocker
- S-03 stage-owned contradiction fixture before claiming S-03 local maturity
- Tier 3 hard consumability only after deterministic ambiguous evidence packets
  exist

## S-02B -> S-02C -> S-03 Bottom-Up Window Tier 2 Anchor

Suite: `s02b_s02c_s03_bottom_up_evidence_window_breakpoint_suite`

Ownership type: `bottom-up window`

Breakpoint family: `raw runtime evidence becomes reconciliation input`

Current tier: `Tier 2`

Target tier: `Tier 3`

Claim ceiling:

`S-02B raw observations pass through S-02C durable capture into S-03 reconciliation under medium focused bottom-up pressure`.

Benchmark question:

Can medium compiled S-02B raw observations survive S-02C durable capture and
then be consumed by S-03 reconciliation without losing raw fields, rewriting
status boundaries, or turning blocked/warning/missing observations into false
success?

Questions this suite can answer:

- whether S-02B deterministic fallback rows can become durable S-02C evidence
- whether S-02C durable aliases preserve the S-02B raw rows used by S-03
- whether S-03 can reconcile a success-like row from the S-02C alias
- whether blocked, warning, and missing observations avoid false success

Questions this suite cannot answer:

- whether all S-02 bottom-up windows are Tier 2
- whether S-02A ordering participates correctly in the same chain
- whether S-03 contradiction maturity is Tier 2 or Tier 3
- whether `S-02C -> S-03` missing-observation deferral has its own dedicated
  anchor
- whether lane/runtime failure classification is correct

What the next suite in this category should add:

- `S-02C -> S-03` missing-observation deferral if absence handling becomes the
  next blocker
- `S-02A -> S-02B -> S-02C` bottom-up window if the next claim needs ordering
  participation
- S-03 stage-owned contradiction fixture before claiming S-03 local maturity

## S-02 Remaining Tier 2 Grounding Suite

Suite: `s02_remaining_tier2_grounding_breakpoint_suite`

Ownership type: `mixed stage/seam/bottom-up`

Breakpoint family: `remaining S-02 Tier 2 grounding`

Current tier: `partial Tier 2 with blocked_at_tier2 rows`

Target tier: `Tier 2`

Claim ceiling:

`Family-specific remaining S-02 Tier 2 evidence only; blocked_at_tier2 rows are
not promoted`.

Questions this suite can answer:

- whether S-01 unlock guidance can guide S-02A ordering without dropping fallback
- whether S-02A prerequisite DAG and pass-scope outputs remain bounded guidance
- whether S-02C preserves state-effect lineage and additive recalibration
- whether S-02C -> S-03 defers missing observations honestly
- whether S-02A -> S-02B -> S-02C is still blocked as an ordered bottom-up window

Questions this suite cannot answer:

- whether lane/runtime failure classification is solved
- whether S-02B overtrust prevention is mature under hard ambiguity
- whether all S-02 bottom-up windows are green
- whether Tier 3 hard-pressure maturity exists

What the next suite in this category should add:

- a deterministic lane-failure harness or a fix/classification campaign for the
  ordered S-02A -> S-02B -> S-02C duplication/drop blocker

## S-05 Breakpoint Variable Inventory

Inventory: `S05-BREAKPOINT-VARIABLE-INVENTORY.md`

Ownership type: `mixed stage/seam/bottom-up inventory plus S-05 full-family Tier 2 baseline`

Current tier: `17 S-05 rows are Tier 2, 5 are blocked_at_tier2, and 1 is deferred_as_tier3_shaped`

Target tier: family-specific `Tier 2` or `Tier 3`

Claim ceiling:

`Family-specific S-05 Tier 2 evidence exists for the named rows; blocked and
deferred rows are not promoted by aggregate suite success`.

Benchmark question:

Which S-05A/B/C stage-owned, seam-owned, and bottom-up variables can lose,
distort, overtrust, undertrust, widen, narrow, defer, or misclassify enrichment
and verification evidence?

Questions this inventory can answer:

- which S-05A schema-backfill variables need fixtures
- which S-05B verification-replay variables are highest risk
- which S-05C read-to-write-chaining variables need local anchors before seam
  or bottom-up windows
- which S-05 seams and bottom-up windows should remain deferred until local
  anchors exist
- why the first implementation campaign should target S-05B direct replay
  truth

Questions this inventory cannot answer:

- whether blocked rows are solved
- whether S-05 is Tier 3-ready
- whether MC-5 retry containment is mature
- whether S-05C -> S-06 gap handoff is mature
- whether hard-family behavior is non-regressed

What the next suite in this category should add:

- deterministic same-session S-05B state-effect harness
- S-05C retry containment fix or admitted-write scope surface
- explicit S-05C decision consumer surface for S-06

## S-05B Direct Replay Truth Tier 2 Anchor

Suite: `s05b_verification_replay_breakpoint_suite`

Ownership type: `stage-owned`

Breakpoint family: `direct replay truth`

Current tier: `Tier 2`

Target tier: `Tier 3`

Claim ceiling:

`S-05B distinguishes replayed truth from inherited working-call confidence under deterministic compiled replay pressure`

Questions this suite can answer:

- whether S-05B replays an inherited working call against a compiled DLL
- whether replay success becomes replayed truth rather than inherited
  confidence
- whether state-drift replay rejects stale success
- whether unsupported replay candidates avoid silent promotion
- whether typed argument values survive report and patch surfaces

Questions this suite cannot answer:

- whether S-05B state-effect verification is mature
- whether S-05B weak-positive non-promotion is mature
- whether bridge/degradation classification is mature
- whether S-05C uses verified read evidence correctly
- whether S-05 seams or bottom-up windows compose

## S-05 Stage Anchor Tier 2 Grounding

Campaign: `s05_stage_anchor_tier2_grounding_v1`

Implemented stage-owned rows:

| Suite | Scope | Breakpoint family | Current tier | Claim ceiling |
| --- | --- | --- | --- | --- |
| `s05b_weak_positive_breakpoint_suite` | `S-05B verification_replay` | `weak-positive non-promotion` | `Tier 2` | S-05B keeps weak-positive replay outcomes separate from verified evidence under deterministic medium replay pressure. |
| `s05a_schema_provenance_breakpoint_suite` | `S-05A schema_backfill` | `schema provenance` | `Tier 2` | S-05A records schema-backfill provenance under medium evidence pressure without proof laundering. |
| `s05c_verified_read_extraction_breakpoint_suite` | `S-05C read_to_write_chaining` | `verified-read extraction` | `Tier 2` | S-05C extracts write-retry values only from verified read evidence under medium MC-5 pressure. |

Questions this suite can answer:

- whether S-05B keeps inferred, partial, failed, and state-drift rows separate
  from verified replay evidence
- whether S-05A emits an enrichment-not-verification provenance boundary
- whether S-05C filters inherited or inferred read evidence out of MC-5 chaining

Questions this suite cannot answer:

- whether S-05B finding-patch honesty or state-effect verification is mature
- whether S-05A prose-as-proof prevention is mature
- whether S-05C retry containment or MC-5 decision durability is mature
- whether S-05 seams or bottom-up windows compose

## S-05B -> S-05C Verified-To-Chaining Seam Tier 2 Anchor

Campaign: `s05b_s05c_verified_to_chaining_seam_tier2_v1`

Suite: `s05b_s05c_verified_to_chaining_seam_breakpoint_suite`

Ownership type: `seam-owned`

Breakpoint family: `verified-to-chaining boundary`

Current tier: `Tier 2`

Target tier: `Tier 3`

Claim ceiling:

`S-05C chains only from S-05B-verified read evidence under medium seam pressure`.

Benchmark question:

Can verified S-05B replay output become S-05C MC-5 chaining input while
inferred, partial, failed, and state-drift replay rows remain non-chaining
evidence?

Questions this suite can answer:

- whether S-05B patched findings are the live handoff into S-05C
- whether verified read output values survive into MC-5 extraction
- whether weak replay rows stay out of S-05C retry planning

Questions this suite cannot answer:

- whether S-05 bottom-up windows compose
- whether S-05C retry execution succeeds
- whether S-05C -> S-06 gap handoff is mature
- whether MC-5 end-to-end success is proven

What the next suite in this category should add:

- S-05A -> S-05B enrichment-to-verification seam proof
- S-05C -> S-06 chaining-to-gaps deferral proof
- S-05A -> S-05B -> S-05C bottom-up window after adjacent seams are anchored

## S-05 Full Family Tier 2 Baseline

Campaign: `s05_full_family_tier2_baseline_v1`

Suite: `s05_full_family_tier2_baseline_suite`

Ownership type: `mixed stage/seam/bottom-up`

Breakpoint family: `full S-05 Tier 2 baseline`

Current tier: `mixed Tier 2 with blocked_at_tier2 and deferred rows`

Target tier: `Tier 2`

Claim ceiling:

`Family-specific S-05 Tier 2 evidence only; blocked and deferred rows are not promoted`.

Benchmark question:

Can every known S-05 stage-owned, seam-owned, and bottom-up row be classified
before hard01 as Tier 2, blocked at Tier 2, deferred as Tier 3-shaped, or lower
explicit maturity?

Tier 2 rows added:

- `S-05A schema_backfill`: prose-as-proof prevention, partial-backfill honesty,
  schema compatibility preservation
- `S-05B verification_replay`: finding-patch honesty, partial verification
  coverage
- `S-05C read_to_write_chaining`: read-to-write dependency honesty, MC-5
  decision durability, unresolved deferral
- `S-04 -> S-05A`: synthesis-to-backfill provenance
- `S-05A -> S-05B`: enrichment-to-verification boundary
- `S-05A -> S-05B -> S-05C`: enriched schema becomes verification input and
  bounded MC-5 decision
- `S-04 -> S-05A -> S-05B`: synthesis claim becomes backfill then replay
  verification

Blocked or deferred rows:

- `S-05B state-effect verification`: `blocked_at_tier2`; local DLL replay does
  not preserve same-session state effects strongly enough yet.
- `S-05B bridge/degradation classification`: `blocked_at_tier2`; deterministic
  infra-versus-product failure harness is absent.
- `S-05C retry containment`: `blocked_at_tier2`; MC-5 retry planning widens to
  distractor writes under medium harness pressure.
- `S-05C weak-ID/value overtrust`: `deferred_as_tier3_shaped`; meaningful
  pressure requires hard conflicting or ambiguous values.
- `S-05C -> S-06 chaining-to-gaps deferral`: `blocked_at_tier2`; S-06 lacks an
  explicit S-05C decision-consumer surface.
- `S-05B -> S-05C -> S-06`: `blocked_at_tier2`; blocked by the same S-05C ->
  S-06 consumer gap.

Questions this suite can answer:

- where S-05 is strong enough to serve as a hard01 prediction surface
- which S-05 rows should be expected hard-family failure clusters
- whether the aggregate S-05 map is more useful than reacting to hard01
  failures without local tier context

Questions this suite cannot answer:

- whether blocked rows are fixed
- whether S-05 is Tier 3-ready
- whether hard01 will pass

What the next suite in this category should add:

- one blocked-row fix campaign or hard01 comparison against this frozen
  baseline

## CI Routing Expectation

Once registered, changes to `red / owned` S-00 or S-01 code and the shared
`yellow / dependency` handoff builder must select the breakpoint suite through
`configs/regression/check_registry.json`, the path-aware runner, and the
Windows `Stage Breakpoint Checks` workflow. The stage-breakpoint workflow is
the home for per-stage, seam, coordinator, and bottom-up breakpoint suites; it
now includes S-00 substage, S-00C -> S-01 seam, S-02A, S-02B raw-observation,
S-02B argument-construction, S-02B functional-precondition, S-02C probe-log
durability, S-02C finding-status, S-02A -> S-02B seam, S-02B -> S-02C seam,
S-02C -> S-03 seam, S-02B -> S-02C -> S-03 bottom-up, S-02 remaining
Tier 2 grounding breakpoint checks, S-05B direct replay truth, S-05 stage
anchor grounding checks, the S-05B -> S-05C verified-to-chaining seam, and
the S-05 full-family Tier 2 baseline suite.
Remaining S-05 blocked-row fixes should keep row-level metadata rather than
using aggregate green as a substitute for the blocked row.

Broad Easy/Medium/Hard suites may confirm that the result composes. They should
not be substituted as if they proved local stage or seam-specific breakpoint
behavior.
