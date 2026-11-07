# Pipeline Proving Baseline Snapshots

## Purpose

This file records point-in-time proving baselines before expensive or
hard-family runs such as `hard01` and `hard02`.

`STAGE-PROVING-MAP.md` is the live map and will change as stages, seams,
coordinators, and bottom-up windows mature. This file preserves the baseline
that existed before a major run so later analysis can ask:

`Did the hard-family failure confirm a known weak point, expose a new blocker
family, or contradict our tier claims?`

## Source Of Truth Relationship

| Surface | Role |
| --- | --- |
| `STAGE-PROVING-MAP.md` | Live pipeline-wide proving map. |
| `S02-BREAKPOINT-VARIABLE-INVENTORY.md` | S-02-specific breakpoint detail and blocker rationale. |
| Dynamic campaign closeouts | Evidence for what changed in a tranche. |
| This file | Frozen pre-run proving baseline snapshots for later hard-run comparison. |
| `.agents/ARCHITECTURAL-WEAKNESSES.md` or family-blocker writebacks | Repeated blocker families after comparison confirms they are architectural. |
| `ENTERPRISE-SURVIVABILITY-SUITE.md` | Separate fail-closed diagnosability ladder that gates whether hard-family runs are usable as semantic comparison surfaces. |
| `HARD-FAMILY-MEASUREMENT-FABRIC.md` | Adjacent measurement-fabric inventory for runner/API/discovery/bridge/Ghidra/artifact authority that must be routable before semantic hard-family interpretation. |
| `HARD-FAMILY-MEASUREMENT-CONTROL-PLANE.md` | Traffic-light admission contract for hard-family lane and bridge scheduling before analyzer work starts. |
| `HARD-FAMILY-FAILURE-SIGNAL-MAP.md` | Canonical key/value routing map from hard/full-suite failure signals to breakpoint owners, row states, confidence, and next campaigns. |
| `COMPILED-SUITE-GREEN-CONTRACT.md` | Green-label contract that prevents compatibility/regression green from being mistaken for product-green. |

## Snapshot Rules

- Take a snapshot before `hard01`, `hard02`, Batch-style pressure, or any
  expensive full-suite run meant to assess pipeline strength.
- Each snapshot must name the commit SHA, hosted baseline posture, known Tier 2+
  anchors, `blocked_at_tier2` rows, unproven critical windows, and the expected
  failure areas.
- After the run, append a comparison row that classifies observed failures as:
  `confirmed_known_weakness`, `new_blocker_family`, `contradicts_tier_claim`,
  `composition_only`, or `infra_or_lane_noise`.
- After the run, update or validate `HARD-FAMILY-FAILURE-SIGNAL-MAP.md` so raw
  hard/full-suite observations become routable keys before branch choice.
- Do not rewrite old snapshots when the live proving map changes. Add a new
  snapshot instead.

## Compiled-Suite Green Contract Gate

`compiled_suite_product_green_contract_v1` freezes product-green claims until a
compiled enterprise run proves the product route:

`compiled/no-source input -> Ghidra-backed analysis -> durable discovery evidence -> semantic/product result`

Historical `Medium01` green is preserved as `compatibility_green` or regression
green unless a run also proves Ghidra-backed route authority. Hard-family
bounded baseline attempts remain measurement/classification evidence until the
active route blocker is resolved and decision-bearing product evidence exists.

This is a confidence-label reset, not a runtime regression. It changes the
claim ceiling for old green wording without deleting the historical evidence.

## Easy01 Product Route Variant

`easy01_product_green_route_probe_v1` adds a separate Easy01 product-route
runner:

```text
scripts/runs/run_spectrum_compiled_easy01_product.py
```

The historical Easy01 runner remains compatibility/regression green. The
product variant reuses the Easy01 chain, sets `ghidra_required=true` for every
target, emits product-green contract fields, preserves dependency blocking, and
cannot claim product green from PE-only, non-comparable, yellow/red/quarantined,
dependency-blocked, or setup-failed evidence.

First bounded product-route proof:

| Field | Value |
| --- | --- |
| `output_root` | `.tmp/easy01-product-green-route-probe-v1/product-proof` |
| `green_contract_level` | `not_green` |
| `blocking_signal` | `api_identity_unavailable` |
| `interpretation` | Product-runner setup failed closed before target execution because API OpenAPI identity was unavailable. This is not Easy01 product evidence and not a semantic failure. |

The next Easy01 product-route step is restoring/verifying the local API and
bridge lane, then rerunning this product probe once. Product-green remains
frozen until the full Easy01 chain has Ghidra-backed route authority and
decision-bearing semantic evidence.

Lane-restore rerun:

| Field | Value |
| --- | --- |
| `output_root` | `.tmp/easy01-product-route-lane-identity-restore-v1/product-proof` |
| `target_reached` | `session_bootstrap` |
| `green_contract_level` | `measurement_green` |
| `blocking_signal` | `post_explore_verdict_fetch_connection_reset` |
| `interpretation` | The managed local API and bridge lane were restored and proved green via startup plus smoke packets, but Easy01 product classification still stopped after terminal explore because verdict retrieval reset before decision-bearing route authority could close. |

Single-entrypoint rerun:

| Field | Value |
| --- | --- |
| `output_root` | `.tmp/local-product-suite-single-entrypoint-v1/easy01` |
| `operator_entrypoint` | `runtime/run-local-product-suite.ps1 -Suite easy01` |
| `lane_startup` | `passed` |
| `target_reached` | `reservation_stage` |
| `green_contract_level` | `measurement_green` |
| `blocking_signal` | `analyzer_timeout` |
| `interpretation` | The single runtime entrypoint now starts or reuses the canonical managed lane before invoking the Easy01 product runner. `session_bootstrap` produced Ghidra-backed route authority and decision-bearing semantic evidence, then `reservation_stage` stalled non-comparably in analyze. The sharper analyzer-runtime packet routes that timeout to `child_wrapper_process_wait_stall`, so the active blocker is no longer lane setup or verdict fetch. |

Child-wrapper rerun:

| Field | Value |
| --- | --- |
| `output_root` | `.tmp/reservation-stage-child-wrapper-process-wait-stall-v1/easy01` |
| `operator_entrypoint` | `runtime/run-local-product-suite.ps1 -Suite easy01` |
| `lane_startup` | `passed` |
| `target_reached` | `reservation_stage` |
| `green_contract_level` | `measurement_green` |
| `blocking_signal` | `ghidra_required_not_entered` |
| `interpretation` | The new parent-side wrapper diagnostics were installed, but the latest bounded proof did not reproduce `child_wrapper_process_wait_stall`. `session_bootstrap` remained comparable, while `reservation_stage` failed closed much earlier: `discovery-output-authority.json` recorded `ghidra_required_not_entered`, `subprocess_returncode=3221225786`, import/bootstrap stderr, no child runtime diagnostic, and no discovery files. Latest-proof-wins moves the Easy01 product route back to Ghidra-route entry, not wrapper wait. |

Run-completion stability rerun:

| Field | Value |
| --- | --- |
| `output_root` | `.tmp/easy01-run-completion-stability-v1/cycle-02` |
| `operator_entrypoint` | `runtime/run-local-product-suite.ps1 -Suite easy01` |
| `lane_startup` | `passed` (`startup_mode=managed_lane_no_reload`) |
| `green_contract_level` | `measurement_green` |
| `blocking_signal` | `session_capture` |
| `interpretation` | Easy01 now completes the full product-route chain from the single entrypoint. `session_bootstrap`, `reservation_stage`, and `release_commit` are route-authoritative, comparable, and decision-bearing. The remaining blocker is later: `audit_trace` completes semantically but closes non-authoritatively with `failure_domain=session_capture`, `save_session_exit=1`, invalid run-validity, and missing decision-bearing run authority. |

Audit-trace authority rerun:

| Field | Value |
| --- | --- |
| `output_root` | `.tmp/easy01-audit-trace-session-capture-authority-v1/proof-01` |
| `operator_entrypoint` | `runtime/run-local-product-suite.ps1 -Suite easy01` |
| `lane_startup` | `passed` (`startup_mode=managed_lane_no_reload`) |
| `green_contract_level` | `product_green` |
| `blocking_signal` | `` |
| `interpretation` | The shared enrichment-to-schema naming seam now carries semantic parameter names through saved-session closeout. `audit_trace` closes with `authoritative_proving=true`, `run_validity_true`, and `session_capture_complete`, so Easy01 reached current-code `product_green` candidate evidence. |

Baseline-promotion confirmation rerun:

| Field | Value |
| --- | --- |
| `output_root` | `.tmp/easy01-product-green-baseline-promotion-v1/confirmation-01` |
| `operator_entrypoint` | `runtime/run-local-product-suite.ps1 -Suite easy01` |
| `lane_startup` | `passed` (`startup_mode=managed_lane_no_reload`) |
| `green_contract_level` | `product_green` |
| `blocking_signal` | `` |
| `interpretation` | The confirmation rerun reproduced Easy01 `product_green` cleanly through the canonical entrypoint and produced a candidate pinned root at `configs/regression/pinned_baselines/spectrum_transaction_release_settlement_suite/easy-01/20260423-135053`, but promotion remained provisional pending a gate-style stability check. |

Baseline-promotion gate rerun:

| Field | Value |
| --- | --- |
| `output_root` | `.tmp/easy01-product-green-baseline-promotion-v1/regression-gate` |
| `operator_entrypoint` | `python scripts/regression/run_regression_gate_v1.py --config configs/regression/gate_v1.json --surfaces lane_trust,easy-01 --fail-fast` |
| `lane_startup` | `passed` |
| `green_contract_level` | `measurement_green` |
| `blocking_signal` | `session_capture` |
| `interpretation` | The same code contradicted the confirmation proof on the very next Easy01 gate-style rerun. `lane_trust` stayed green, but `audit_trace` regressed to `save_session_exit=1`, `run_validity_false`, non-decision-bearing `run_authority`, and top-level `blocking_signal=session_capture`. By promotion law, Easy01 was not blessed as the defended baseline and the historical Gate V1 Easy01 surface remained active. |

Confirmation-stability reruns:

| Field | Value |
| --- | --- |
| `output_root` | `.tmp/easy01-product-green-confirmation-stability-v1/confirmation-01` |
| `operator_entrypoint` | `runtime/run-local-product-suite.ps1 -Suite easy01` |
| `lane_startup` | `passed` (`startup_mode=managed_lane_no_reload`) |
| `green_contract_level` | `product_green` |
| `blocking_signal` | `` |
| `interpretation` | After making S-07 contract emission deterministic and adding a bounded required-artifact barrier before session capture trust, the canonical Easy01 rerun stayed `product_green` with `authoritative_proving=true`. |

Confirmation-stability product gate rerun:

| Field | Value |
| --- | --- |
| `output_root` | `.tmp/easy01-product-green-confirmation-stability-v1/regression-gate` |
| `operator_entrypoint` | `python scripts/regression/run_regression_gate_v1.py --config .tmp/easy01-product-green-confirmation-stability-v1/gate-config.json --surfaces lane_trust,easy-01 --fail-fast` |
| `lane_startup` | `passed` |
| `green_contract_level` | `product_green` |
| `blocking_signal` | `` |
| `interpretation` | The product-style gate rerun also stayed `product_green` against the candidate Easy01 product baseline. The prior contradiction at `audit_trace` / `session_capture` did not reproduce, so Easy01 now holds green across both same-code rerun shapes. Baseline promotion can return as a narrower follow-up campaign. |

Baseline-promotion v2 confirmation rerun:

| Field | Value |
| --- | --- |
| `output_root` | `.tmp/easy01-product-green-baseline-promotion-v2/confirmation-01` |
| `operator_entrypoint` | `runtime/run-local-product-suite.ps1 -Suite easy01` |
| `lane_startup` | `passed` |
| `green_contract_level` | `product_green` |
| `blocking_signal` | `` |
| `promoted_pinned_root` | `configs/regression/pinned_baselines/spectrum_transaction_release_settlement_suite/easy-01/20260423-151031` |
| `interpretation` | The fresh v2 confirmation reproduced Easy01 `product_green` through the canonical entrypoint with route authority, comparability, semantic proof, and decision-bearing run authority present. This root became the candidate active pinned baseline. |

Baseline-promotion v2 Gate V1 rerun:

| Field | Value |
| --- | --- |
| `output_root` | `.tmp/easy01-product-green-baseline-promotion-v2/regression-gate` |
| `operator_entrypoint` | `python scripts/regression/run_regression_gate_v1.py --config configs/regression/gate_v1.json --surfaces lane_trust,easy-01 --fail-fast` |
| `overall_verdict` | `pass` |
| `surface_verdicts` | `lane_trust=pass`, `easy-01=pass` |
| `active_easy01_baseline` | `configs/regression/pinned_baselines/spectrum_transaction_release_settlement_suite/easy-01/20260423-151031` |
| `interpretation` | The checked-in Gate V1 path now dispatches Easy01 through `runner_id=easy01_product`, requires product-green summary/report fields, and passed against the new pinned root. Easy01 is promoted as the defended product-green baseline; the old `20260410-082334` root is historical compatibility evidence. |

## Medium01 Product Route Variant

`medium01_product_green_route_probe_v1` adds a separate product-route runner:

```text
scripts/runs/run_spectrum_compiled_medium01_product.py
```

The historical Medium01 runner remains compatibility/regression green. The
product variant reuses the Medium01 target chain, sets `ghidra_required=true`
for every target, and emits `green_contract_level`, `product_green_eligible`,
route-authority, comparability, semantic-proof, authoritative-proving, and
blocking-signal fields. A non-comparable predecessor must stop dependent
targets as `dependency_blocked`; yellow, red, quarantined, dependency-blocked,
or PE-only evidence cannot satisfy product green.

First bounded product-route proof:

| Field | Value |
| --- | --- |
| `output_root` | `.tmp/medium01-product-green-route-probe-proof` |
| `green_contract_level` | `not_green` |
| `blocking_signal` | `bridge_identity_unavailable` |
| `interpretation` | Product-runner setup failed closed before target execution; this is not Medium01 product evidence and not a semantic failure. |

Bridge-identity restore proof:

| Field | Value |
| --- | --- |
| `output_root` | `.tmp/medium01-product-route-bridge-identity-restore/product-proof` |
| `bridge_smoke` | `bridge_identity_green` |
| `target_reached` | `session_bootstrap` |
| `green_contract_level` | `measurement_green` |
| `blocking_signal` | `product_route_gap` |
| `interpretation` | Bridge setup is no longer the active blocker; the product runner now needs route-authority harvesting/wiring before Medium01 can claim product-route progress. |

Route-authority wiring proof:

| Field | Value |
| --- | --- |
| `output_root` | `.tmp/medium01-product-route-authority-wiring/product-proof` |
| `target_reached` | `session_bootstrap` |
| `green_contract_level` | `measurement_green` |
| `blocking_signal` | `post_explore_verdict_fetch_connection_reset` |
| `interpretation` | Ghidra-backed saved-session evidence can now be harvested into `product-route-authority.json`, but the proof stopped when post-explore verdict retrieval reset before decision-bearing route authority could close. |

Completion/stability proof:

| Field | Value |
| --- | --- |
| `output_root` | `.tmp/medium01-product-green-completion-stability-v1/medium01` |
| `operator_entrypoint` | `runtime/run-local-product-suite.ps1 -Suite medium01` |
| `targets_completed` | `session_bootstrap`, `reservation_stage`, `dispatch_preview`, `fee_quote`, `settlement_reconcile` |
| `green_contract_level` | `product_green` |
| `product_green_eligible` | `true` |
| `route_authority_present` | `true` |
| `safe_to_compare` | `true` |
| `authoritative_proving` | `true` |
| `blocking_signal` | none |
| `interpretation` | Bounded post-explore verdict/findings retrieval retry repaired the transient connection-reset seam without weakening route authority. Medium01 completed the full product chain as baseline-ready product-green evidence. |

Same-code confirmation:

| Field | Value |
| --- | --- |
| `output_root` | `.tmp/medium01-product-green-completion-stability-v1/medium01-confirmation` |
| `green_contract_level` | `product_green` |
| `product_green_eligible` | `true` |
| `route_authority_present` | `true` |
| `safe_to_compare` | `true` |
| `authoritative_proving` | `true` |
| `blocking_signal` | none |
| `interpretation` | The same-code confirmation held product green through the canonical product-suite entrypoint. Medium01 is ready for a separate baseline-promotion decision, but this snapshot does not promote the active registry or Gate V1 baseline. |

## Hard-Family Readiness Gate

hard01/hard02 semantic comparison was paused until enterprise survivability
Tier 2 runner integration existed. The first post-ladder hard01 comparison
closed with non-comparable target packets and a final suite packet, so the
measurement terminalization contract held. A later bounded lane-identity proof
made `session_bootstrap` comparable. The analyzer-authority proof now
classifies `reservation_stage` as non-comparable `discovery_empty` with no
durable discovery artifacts.

Current posture:

| Surface | State | Interpretation |
| --- | --- | --- |
| hard01/hard02 semantic comparison | bounded hard01 comparison run, still semantically blocked | lane identity comparability is repaired; `reservation_stage` now blocks in the measurement fabric at `bridge_stream_no_heartbeat` sharpened from `analyzer_timeout` after Ghidra-first route authority |
| hard-family measurement terminalization | prerequisite evidence | non-comparable packets are baseline data, not semantic proof |
| enterprise survivability | Tier 3 runner-equivalent compiled fixture ladder plus hard01 non-comparable closeout, lane identity comparability guard, and analyzer-authority classifier evidence | Tier 4 is deferred until reservation-stage discovery output is repaired or explicitly unsupported |
| hard-family measurement fabric | Tier 5 hard01 readiness gate implemented over existing guards and bounded hard01 baseline classification completed | bridge-health admission, Tier 2 enforcement, Tier 3 selected routing, and Tier 4 quarantine held; post-explore fail-closed guard exists; Ghidra-first route authority prevents PE-only hard-family discovery from becoming comparable and latest proof routes to bridge/Ghidra runtime |
| hard-family measurement control plane | Tier 5 hard01 readiness verdict implemented after Tier 4 configured quarantine/recovery selection and consumed by `hard01_bounded_baseline_attempt_v1` | hard01/hard02 select from configured bridge candidates, pass the selected bridge URL into managed analyze, avoid active bridge/target/profile quarantine rows, and emit `ready_for_bounded_hard01_baseline_attempt` or a specific not-ready verdict; bounded baseline showed the control plane can classify the run but live multi-bridge route proof and runtime parallel scheduling remain future claims |

### Lane Identity Comparability Gate

`hard_family_lane_identity_comparability_v1` makes runner/API/bridge identity a
hard-family comparability prerequisite. For v1 local hard-family evidence, the
runner, API, and bridge must share the current repo git SHA. A successful target
without that identity parity is operational output, not comparable semantic
evidence. Managed stale local processes should restart; unmanaged or
restart-suppressed stale processes remain non-comparable with a named verdict.
The bounded proof run made `session_bootstrap` comparable and decision-bearing;
the next blocker is `reservation_stage` discovery output production.

### Hard-Family Analyze/Discovery Authority Gate

`hard_family_analyze_discovery_authority_v1` treats `reservation_stage` as the
first hard-shaped proof case for analyzer authority. The bounded proof produced
a durable non-comparable analyzer packet with `reason_code: discovery_empty`,
`safe_to_compare: false`, `discovery_output_present: false`, and checked output
paths. The classifier distinguishes `analyzer_timeout`, `discovery_empty`,
`output_missing`, and `analyzer_error` without promoting hard01 semantic
maturity.

### Hard-Family Measurement Fabric Gate

`hard_family_measurement_fabric_inventory_v1` gives the runner/API/discovery
subprocess/bridge/Ghidra/artifact authority network a dedicated adjacent proving
axis. This prevents measurement failures from being misread as S-00 through
S-07 stage failures. The current known bridge-stream signal is
`bridge_stream_no_heartbeat`, but the active routed key is now
`control_plane_green_but_bridge_stalled` because
`measurement_control_plane_passive_bounded_proof_v1` admitted
`reservation_stage` as green before that bridge stall.

### Hard-Family Measurement Control-Plane Gate

`hard_family_measurement_control_plane_design_v1` defines the traffic-light
admission layer for continuous baseline runs, and
`measurement_control_plane_passive_observation_v1` emits that packet into
hard-family suite and per-target run output without changing scheduling.
`measurement_control_plane_passive_bounded_proof_v1` then proved the packet
surface was too optimistic for bridge health: `reservation_stage` was green
while the bridge stream produced no heartbeat.
`hard_family_control_plane_bridge_health_signal_v1` adds passive bridge-health
inputs so unproven stream health becomes `bridge_stream_health_unproven` and
recent no-heartbeat evidence becomes `bridge_recent_no_heartbeat_stall`. The
bounded proof also observed `analyzer_launch_connection_reset` after diagnostic
scheduling, which is a fallback analyzer-launch signal if it recurs.
`hard_family_bridge_lease_and_health_gate_v1` makes those traffic lights
binding for hard-family targets: yellow can run only as diagnostic evidence, and
red/quarantined lanes fail closed before `run_one`. This is a measurement
admission/enforcement claim only; hard01 semantic comparison stays paused until
the bounded enforcement proof is coherent and the bridge/analyzer blocker is no
longer active.

`measurement_control_plane_tier3_bridge_candidate_registry_v1` adds a pure
candidate-registry helper. It proves the control plane can choose a green bridge
over yellow/red/quarantined alternatives, choose yellow only as diagnostic
fallback, and fail closed when no runnable candidate exists. It does not yet
make hard-family runners acquire a real multi-bridge lease.
`measurement_control_plane_tier3_runner_candidate_consumption_v1` wires that
registry packet shape into hard01/hard02 through the configured local bridge as
a single candidate. The next unproven surface is real multi-bridge candidate
discovery and scheduling.
`measurement_control_plane_tier3_multi_bridge_candidate_discovery_v1` adds pure
configured-candidate discovery. It normalizes bridge URLs and associated
identity/readiness/health/quarantine metadata into registry candidate rows, but
does not contact bridges or schedule work.
`measurement_control_plane_tier3_runner_multi_bridge_selection_v1` makes the
selection operational for hard01/hard02: the selected configured bridge URL is
passed through the runner, `ApiClient.analyze`, `/api/analyze`, and discovery's
bridge call. The API guard rejects unallowlisted or non-local selected bridge
URLs. This is still sequential routing, not parallel bridge execution.
`measurement_control_plane_tier4_bridge_quarantine_recovery_v1` adds configured
quarantine/recovery selection. Active quarantine rows can block one bridge,
target, and analysis profile without poisoning unrelated targets; expired and
cleared rows remain visible but do not block scheduling.
`measurement_control_plane_hard01_baseline_readiness_gate_v1` adds the
machine-readable readiness verdict that decides whether the next action may be a
bounded hard01 baseline attempt. The verdict can be
`ready_for_bounded_hard01_baseline_attempt` or a not-ready key for control-plane,
lane identity, packet terminalization, dependency blocking, or selected-bridge
routing gaps. The bounded readiness proof emitted
`ready_for_bounded_hard01_baseline_attempt` while preserving
`reservation_stage` as non-comparable `analyzer_timeout`. This is still not a
hard01 maturity claim.

`hard01_bounded_baseline_attempt_v1` consumed that readiness verdict. The run
made `session_bootstrap` comparable and decision-bearing, then stopped at
`reservation_stage` with yellow diagnostic-only control-plane admission,
non-comparable `analyzer_timeout`, analyzer-runtime `worker_startup_stall`, and
seven downstream `dependency_blocked` targets. This is bounded classification
evidence only; no stage row, survivability tier, or hard01 maturity claim is
promoted.

`reservation_stage_analyzer_runtime_progress10_stall_v1` then checked whether
the progress-10 boundary was truly the current blocker. The bounded proof did
not reproduce the progress-10 stop. It reached progress `30`,
`worker_before_discovery`, `_run_discovery`, and
`discovery_child_launch_attempted`, then timed out with no child PID, child
diagnostic, bridge attempt, or discovery output. Latest-proof-wins moves the
active measurement-fabric key to `discovery_child_launch_missing`.

`reservation_stage_discovery_child_launch_boundary_v1` then checked that child
launch boundary. The bounded proof reached `discovery_child_popen_calling` and
`discovery_child_started` with child PID `38940`, then timed out without child
completion, child return code, bridge attempt, or discovery output. That moved
the measurement-fabric key to `discovery_child_running_no_output`.

`reservation_stage_discovery_child_runtime_no_output_v1` added child-owned
runtime phase diagnostics and fixed discovery-output detection so diagnostic
JSON cannot masquerade as discovery output. Its corrective proof observed a
useful known signal, `child_wrapper_process_wait_stall`: the real Python child
recorded `bootstrap_main_returned` and wrote MCP output while the wrapper/Popen
process did not return. The final current-code bounded proof did not reproduce
that child-runtime path; it stopped at progress `10` with no post-progress-10
marker. Latest-proof-wins moves the active measurement-fabric key to
`post_progress_10_control_stall`.

`reservation_stage_post_progress_10_control_stall_v1` added out-of-band
progress-10 worker breadcrumbs and runner-side classifier routing for
`progress_10_status_persist_stall`, `progress_10_authority_emit_stall`,
`progress_10_authority_return_marker_missing`,
`progress_30_persist_start_missing`, `worker_pre_progress_30_exception`, and
`status_persistence_stale`. Its bounded proof did not reach `reservation_stage`:
`session_bootstrap` reached terminal explore status, then the runner crashed
fetching `/api/jobs/{job_id}/verdict` after a connection reset. That key is now
covered by bounded retry plus existing fail-closed authority: transient resets
can recover, while persistent verdict/findings fetch failures still produce
non-authoritative closeout instead of semantic overclaim.

`hard_family_post_explore_artifact_fetch_fail_closed_v1` adds focused
fail-closed coverage for verdict and findings retrieval after terminal explore.
The runner now writes post-explore artifact-fetch authority, measurement
terminalization, job terminalization, run authority, and run result packets
instead of crashing when verdict or findings route fetches fail. A bounded proof
then reached `reservation_stage` without reproducing the post-explore fetch
reset. Latest-proof-wins routes to `child_pe_export_close_keyboard_interrupt`:
the discovery child detects `SP_IssueReleaseHold`, then receives
`KeyboardInterrupt` during PE export parsing cleanup in `pefile.py` /
`gc.collect`, leaving no discovery files. This is still measurement-fabric
evidence, not hard01 semantic maturity.

`reservation_stage_ghidra_first_discovery_routing_v1` reclassifies that finding
as route-authority drift before PE-parser repair. Hard-family `strict_dll`
targets now mark `ghidra_required`; PE structural output remains diagnostic, but
PE-only discovery cannot satisfy comparable hard-family evidence when Ghidra is
required. Its bounded proof made `session_bootstrap` comparable and moved
`reservation_stage` past the PE parser path to progress `60` / "calling Windows
GUI bridge", then terminalized non-comparably as `analyzer_timeout` with
`bridge-analyzer-authority.json` reason `bridge_stream_no_heartbeat`.
Hard01 semantic comparison remains paused until bridge/Ghidra runtime authority
produces Ghidra-backed output or a sharper durable non-comparable owner key.

## Snapshot 2026-04-20: Post S-02 Remaining Tier 2 Grounding

| Field | Value |
| --- | --- |
| `snapshot_id` | `2026-04-20-s02-remaining-tier2-grounding` |
| `commit` | `5bbbc4b406fa65a24d1a9e56261f8bcd1128615d` |
| `baseline_posture` | Hosted Fast Checks, Stage Breakpoint Checks, Required Regression Gates, and Medium01 Checkpoints green on commit `5bbbc4b4`. |
| `claim_ceiling` | Family-specific Tier 2 evidence. This is not a whole-pipeline strength claim and not an all-S-02 Tier 2 claim. |
| `live_map_source` | `STAGE-PROVING-MAP.md` at commit `5bbbc4b4`. |
| `s02_detail_source` | `S02-BREAKPOINT-VARIABLE-INVENTORY.md` at commit `5bbbc4b4`. |

### Pipeline Proving Dashboard At Snapshot

| Category | Current state | Interpretation |
| --- | --- | --- |
| Stage-owned rows | 10 are Tier 2, 2 are `blocked_at_tier2`, and S-01 has seam participation only | S-02 is materially stronger, but some critical execution-ownership questions remain unresolved. |
| Seam-owned rows | 5 are Tier 2, 1 is Tier 1, and 3 remain `planned/0` | S-02 seams have meaningful proof, but downstream S-03/S-04 and some S-02A/S-02B pressure remain open. |
| Coordinator rows | planned; no implemented coordinator exists | Coordinator proving remains future work. |
| Bottom-up windows | 1 is Tier 2, 1 is `blocked_at_tier2`, and 1 remains `planned/0` | Short-chain composition is partially proven; ordered S-02A participation is not yet trustworthy. |
| Full-suite baselines | Fast/Required/Medium01 green | Broad composition is green, but hard-family behavior should be interpreted against the local proving map. |

### Known S-02 Tier 2 Anchors

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

### Known Blocked Rows Before Hard-Family Comparison

| Scope | Ownership | Blocker | Expected hard-run signal |
| --- | --- | --- | --- |
| `S-02B invocation_execution` | `stage-owned` | `lane/runtime failure classification` is `blocked_at_tier2` because no deterministic lane-failure harness separates infrastructure failure from compiled product-call failure. | Hard-family failures may blur product failure and lane instability. Treat any such signal as expected weakness until a lane-failure harness exists. |
| `S-02B invocation_execution` | `stage-owned` | `S-02B overtrust prevention` is `blocked_at_tier2`; meaningful proof needs hard ambiguity rather than a shallow Tier 2 fixture. | Hard-family failures may show S-02B acting too aggressively on weak static/unlock guidance. |
| `S-02A -> S-02B -> S-02C` | `bottom-up window` | Ordered evidence window is `blocked_at_tier2`; attempted fixture exposed duplicate read execution and dropped write execution under ordered S-02A scope. | Hard-family failures may show planned work not matching executed/durable evidence, especially when S-02A ordering participation matters. |

### Expected Comparison Questions For hard01/hard02

Use these questions after a hard-family run:

- Did failures cluster around known S-02B lane/runtime ownership ambiguity?
- Did failures show S-02B overtrusting weak guidance or invoking unsupported work?
- Did failures show S-02A ordered work being duplicated, widened, reordered, or dropped before S-02C durability?
- Did any failure contradict an existing Tier 2 claim, such as raw observation integrity or S-02C durability?
- Did hard-family behavior expose a new stage, seam, coordinator, or bottom-up breakpoint family not represented in `STAGE-PROVING-MAP.md`?

## Hard-Run Comparison Log

| Run | Compared against snapshot | Classification | Notes | Follow-up |
| --- | --- | --- | --- | --- |
| `hard01_against_enterprise_survivability_ladder_v1` | `enterprise_survivability_compiled_fixture_ladder_v1` | `confirmed_known_weakness` + `lane_or_infra_noise` | Hard01 wrote a final survivability packet with 0 comparable, 2 non-comparable, and 7 dependency-blocked targets. `reservation_stage` terminalized as `discovery_empty`; `session_bootstrap` completed but stayed non-comparable due API/bridge git identity mismatch. | Repair live lane comparability before Tier 4 recovery pressure or semantic hard-family claims. |
| `pending` | `2026-04-20-s02-remaining-tier2-grounding` | `pending` | No hard-family comparison recorded yet. | Run hard-family or Batch-style pressure only after deciding the next proving question. |

## Snapshot 2026-04-20: Post S-05 Full Family Tier 2 Baseline

| Field | Value |
| --- | --- |
| `snapshot_id` | `2026-04-20-s05-full-family-tier2-baseline` |
| `commit` | `6227fcd7` |
| `baseline_posture` | Local focused S-05 full-family suite green with blocked rows represented as strict expected failures; hosted Fast, Stage Breakpoint, Required, and Medium01 green for `f3ed7f82`. |
| `claim_ceiling` | Family-specific S-05 Tier 2 evidence. This is not a whole-pipeline strength claim and not an all-S-05 Tier 2 claim because blocked and deferred rows remain explicit. |
| `live_map_source` | `STAGE-PROVING-MAP.md` after `s05_full_family_tier2_baseline_v1`. |
| `s05_detail_source` | `S05-BREAKPOINT-VARIABLE-INVENTORY.md` after `s05_full_family_tier2_baseline_v1`. |

### S-05 Proving Dashboard At Snapshot

| Category | Current state | Interpretation |
| --- | --- | --- |
| Stage-owned rows | 12 are Tier 2, 3 are `blocked_at_tier2`, and 1 is `deferred_as_tier3_shaped` | S-05 local anchors are broad enough for hard-family prediction, but state effects, bridge degradation, retry containment, and hard overtrust remain unresolved. |
| Seam-owned rows | 3 are Tier 2 and 1 is `blocked_at_tier2` | Internal S-05 seams are mostly anchored; S-05C -> S-06 needs an explicit consumer surface. |
| Bottom-up windows | 2 are Tier 2 and 1 is `blocked_at_tier2` | S-05A/B/C and S-04/A/B windows are useful; S-05B/C/S-06 remains blocked by the S-05C -> S-06 seam. |
| Full-suite baselines | Fast/Required/Medium01 remain composition confirmation only | Hard-family failures should be compared against the blocked rows, not used to promote local maturity. |

### Known S-05 Tier 2 Rows

| Scope | Ownership | Breakpoint family |
| --- | --- | --- |
| `S-05A schema_backfill` | `stage-owned` | schema provenance |
| `S-05A schema_backfill` | `stage-owned` | prose-as-proof prevention |
| `S-05A schema_backfill` | `stage-owned` | partial-backfill honesty |
| `S-05A schema_backfill` | `stage-owned` | schema compatibility preservation |
| `S-05B verification_replay` | `stage-owned` | direct replay truth |
| `S-05B verification_replay` | `stage-owned` | weak-positive non-promotion |
| `S-05B verification_replay` | `stage-owned` | finding-patch honesty |
| `S-05B verification_replay` | `stage-owned` | partial verification coverage |
| `S-05C read_to_write_chaining` | `stage-owned` | verified-read extraction |
| `S-05C read_to_write_chaining` | `stage-owned` | read-to-write dependency honesty |
| `S-05C read_to_write_chaining` | `stage-owned` | MC-5 decision durability |
| `S-05C read_to_write_chaining` | `stage-owned` | unresolved deferral |
| `S-04 -> S-05A` | `seam-owned` | synthesis-to-backfill provenance |
| `S-05A -> S-05B` | `seam-owned` | enrichment-to-verification boundary |
| `S-05B -> S-05C` | `seam-owned` | verified-to-chaining boundary |
| `S-05A -> S-05B -> S-05C` | `bottom-up window` | enriched schema becomes verification input and bounded MC-5 decision |
| `S-04 -> S-05A -> S-05B` | `bottom-up window` | synthesis claim becomes backfill then replay verification |

### Known S-05 Blocked Or Deferred Rows Before Hard-Family Comparison

| Scope | Ownership | Blocker | Expected hard-run signal |
| --- | --- | --- | --- |
| `S-05B verification_replay` | `stage-owned` | `state-effect verification` is `blocked_at_tier2`; local DLL replay does not preserve same-session state effects strongly enough yet. | Hard-family failures may show return success without durable state-effect truth, especially for mutator/observer pairs. |
| `S-05B verification_replay` | `stage-owned` | `bridge/degradation classification` is `blocked_at_tier2`; no deterministic infra-versus-product failure harness exists. | Hard-family failures may blur bridge degradation and product-call failure ownership. |
| `S-05C read_to_write_chaining` | `stage-owned` | `retry containment` is `blocked_at_tier2`; medium harness exposes retry widening to distractor writes. | Hard-family failures may show MC-5 trying too many write candidates or using an over-broad retry plan. |
| `S-05C read_to_write_chaining` | `stage-owned` | `weak-ID/value overtrust` is `deferred_as_tier3_shaped`. | Hard-family failures may show ambiguous or stale read values being overtrusted; this should become a Tier 3 fixture, not a shallow Tier 2 row. |
| `S-05C -> S-06` | `seam-owned` | `chaining-to-gaps deferral` is `blocked_at_tier2`; S-06 lacks an explicit S-05C decision-consumer surface. | Hard-family failures may show unresolved MC-5 caveats disappearing before S-06 gap handling. |
| `S-05B -> S-05C -> S-06` | `bottom-up window` | Dependent on the blocked S-05C -> S-06 seam. | Hard-family failures may show verified/chained evidence failing to become reviewable gap decisions. |

### Expected Comparison Questions For hard01/hard02

- Do hard-family failures cluster around S-05 state-effect replay, retry containment, bridge degradation, or S-05C -> S-06 deferral?
- Does any hard-family failure contradict a S-05 Tier 2 claim, especially schema proof boundaries, verified-read extraction, or S-05B -> S-05C verified-to-chaining?
- Does hard-family behavior expose a new S-05 breakpoint family not represented in the inventory?
- Do S-05 failures correlate with the known S-02 blockers, suggesting cross-stage weakness rather than isolated S-05 weakness?

## Snapshot 2026-04-20: Pre Hard01 Pipeline Breakpoint Inventory

| Field | Value |
| --- | --- |
| `snapshot_id` | `2026-04-20-pre-hard01-pipeline-breakpoint-inventory` |
| `commit` | `aac68dbd` |
| `baseline_posture` | Inventory-only snapshot after `s00_to_s07_pipeline_breakpoint_inventory_v1`; no new runtime or fixture maturity claim. |
| `claim_ceiling` | Tier 0 pipeline-wide inventory and prediction surface only. |
| `live_map_source` | `STAGE-PROVING-MAP.md` after pipeline-wide inventory rollup. |
| `detail_sources` | `S00-BREAKPOINT-VARIABLE-INVENTORY.md`, `S01-BREAKPOINT-VARIABLE-INVENTORY.md`, `S02-BREAKPOINT-VARIABLE-INVENTORY.md`, `S03-BREAKPOINT-VARIABLE-INVENTORY.md`, `S04-BREAKPOINT-VARIABLE-INVENTORY.md`, `S05-BREAKPOINT-VARIABLE-INVENTORY.md`, `S06-BREAKPOINT-VARIABLE-INVENTORY.md`, `S07-BREAKPOINT-VARIABLE-INVENTORY.md`. |

### Pipeline Proving Dashboard At Snapshot

| Category | Current state | Interpretation |
| --- | --- | --- |
| Stage-owned rows | 25 are Tier 2, 6 are `blocked_at_tier2`, 1 is `deferred_as_tier3_shaped`, and 35 remain `planned/0` or Tier 3-targeted without local fixtures | S-02 and S-05 are the strongest local proving islands; S-01, S-03, S-04, S-06, and S-07 are mostly unanchored locally. |
| Seam-owned rows | 11 are Tier 2, 1 is Tier 1, 2 are `blocked_at_tier2`, and 4 remain `planned/0` | S-02 and S-05 internal seams have meaningful proof, but S-03 -> S-04, S-06 -> S-07, and S-05C -> S-06 remain key interpretation risks. |
| Coordinator rows | post-S-00 coordinator remains planned | No coordinator claim exists; hard-family failures around S-00/S-01 narrowing may justify coordinator work later. |
| Bottom-up windows | 3 are Tier 2, 2 are `blocked_at_tier2`, and 6 remain `planned/0` | Short-chain composition is only partially proven; hard01 should not be interpreted as broad bottom-up maturity. |
| Full-suite baselines | Broad gates confirm composition only | No broad gate promotes local stage or seam maturity without family-specific evidence. |

### Pipeline Inventory Sources

| Stage family | Detail source | Current posture |
| --- | --- | --- |
| `S-00A/B/C` | `S00-BREAKPOINT-VARIABLE-INVENTORY.md` | one Tier 2 anchor per runtime stage; admission seam only Tier 1 |
| `S-01` | `S01-BREAKPOINT-VARIABLE-INVENTORY.md` | local unlock-owned rows planned/0 |
| `S-02A/B/C` | `S02-BREAKPOINT-VARIABLE-INVENTORY.md` | strong partial Tier 2 baseline with blocked lane/runtime, overtrust, and ordered-window rows |
| `S-03` | `S03-BREAKPOINT-VARIABLE-INVENTORY.md` | local reconciliation rows planned/0 |
| `S-04` | `S04-BREAKPOINT-VARIABLE-INVENTORY.md` | local synthesis rows planned/0 |
| `S-05A/B/C` | `S05-BREAKPOINT-VARIABLE-INVENTORY.md` | full-family baseline with 17 Tier 2, 5 blocked, 1 deferred |
| `S-06` | `S06-BREAKPOINT-VARIABLE-INVENTORY.md` | local gap rows planned/0; S-05C decision consumer blocked |
| `S-07` | `S07-BREAKPOINT-VARIABLE-INVENTORY.md` | S-07 close-path reliability has observed no-close weakness; local finalization rows remain planned/0 |

### Known Expected hard01 Signals

| Scope | Ownership | Known weakness | Expected hard-run signal |
| --- | --- | --- | --- |
| `S-02B invocation_execution` | `stage-owned` | lane/runtime failure classification is `blocked_at_tier2` | Hard-family failures may blur product-call failure and lane instability. |
| `S-02B invocation_execution` | `stage-owned` | overtrust prevention is `blocked_at_tier2` / Tier 3-shaped | Hard-family failures may show unsafe invocation from weak guidance. |
| `S-02A -> S-02B -> S-02C` | `bottom-up window` | ordered evidence window is `blocked_at_tier2` | Hard-family failures may show ordered work duplicated, widened, or dropped before durability. |
| `S-05B verification_replay` | `stage-owned` | state-effect verification is `blocked_at_tier2` | Hard-family failures may show return success without durable state-effect truth. |
| `S-05B verification_replay` | `stage-owned` | bridge/degradation classification is `blocked_at_tier2` | Hard-family failures may blur infrastructure failure and product behavior. |
| `S-05C read_to_write_chaining` | `stage-owned` | retry containment is `blocked_at_tier2` | Hard-family failures may show MC-5 widening retry plans to distractor writes. |
| `S-05C -> S-06` | `seam-owned` | chaining-to-gaps deferral is `blocked_at_tier2` | Hard-family failures may show unresolved MC-5 caveats disappearing before gap handling. |
| `S-06 gaps` | `stage-owned` | local gap handling remains mostly `planned/0` | Hard-family failures may expose repeated-gap, retry-exhaustion, or clarification weakness. |
| `S-07 finalize` | `stage-owned` | close-path reliability has observed no-close signals: `s07_finalize_vocab_persist_no_close`, `s07_macro_verdict_persist_no_close` | Hard-family or Medium01 failures may stall in finalization spans despite completed upstream work. |

### Expected Comparison Questions For hard01

- Do hard01 failures cluster around known S-02 or S-05 blocked rows?
- Do hard01 failures expose S-01, S-03, S-04, S-06, or S-07 rows that are still `planned/0`?
- Does any hard01 failure contradict an existing Tier 2 claim?
- Does the S-07 no-close family block hard-family interpretation before semantic failures can be observed?
- Does hard01 reveal a new breakpoint family missing from the pipeline inventory?

## Snapshot 2026-04-21: Pre Hard01 Full Tier 2 Baseline

| Field | Value |
| --- | --- |
| `snapshot_id` | `2026-04-21-pre-hard01-full-tier2-baseline` |
| `commit` | `6c5bd740` |
| `baseline_posture` | Full-pipeline row-classified Tier 2 baseline after `pipeline_full_tier2_baseline_v1`; failed and blocked rows are preserved as baseline evidence. |
| `claim_ceiling` | Full-pipeline Tier 2 baseline classification only; no hard01 maturity claim. |
| `row_lock` | `dynamic_campaigns/pipeline_full_tier2_baseline_v1/ROW-LOCK.md` |

### Dashboard

| Category | Baseline state |
| --- | --- |
| Stage-owned rows | 32 Tier 2, 1 Tier 1, 2 `failed_tier2`, 10 `blocked_at_tier2`, 21 deferred/planned lower maturity, 1 coordinator-adjacent planned/unimplemented dependency |
| Seam-owned rows | 12 Tier 2, 1 Tier 1, 3 `blocked_at_tier2`, 2 planned lower maturity |
| Coordinator rows | 1 `planned_unimplemented` |
| Bottom-up windows | 3 Tier 2, 3 `blocked_at_tier2`, 5 planned lower maturity |

### Known Failed Or Blocked Signals

| Scope | Baseline state | Expected hard01 signal |
| --- | --- | --- |
| `S-03 contradictory evidence handling` | `failed_tier2` | Hard failures may show unresolved contradiction or overconfident reconciliation. |
| `S-07 close-path reliability` | `failed_tier2` | Hard or Medium failures may stall at finalization or miss terminal close/artifact markers. |
| `S-06 repeated gap-family recognition` | `blocked_at_tier2` | Hard failures may show repeated unresolved items without family grouping. |
| `S-05C -> S-06 chaining-to-gaps deferral` | `blocked_at_tier2` | Hard failures may lose unresolved MC-5 caveats before gap handling. |
| `post-S-00 coordinator` | `planned_unimplemented` | Hard failures involving packet narrowing are coordinator-shaped only if S-00C stays honest and S-01/S-02 consume poorly under pressure. |

### Hard01 Comparison Labels

- `confirmed_known_weakness`: failure matches a failed, blocked, or deferred row.
- `new_blocker_family`: failure has no matching row in the baseline.
- `contradicts_tier_claim`: failure contradicts a row marked Tier 2.
- `composition_only`: local rows hold but the short or broad chain fails.
- `lane_or_infra_noise`: artifact evidence points to lane/runtime infrastructure rather than product or stage behavior.
