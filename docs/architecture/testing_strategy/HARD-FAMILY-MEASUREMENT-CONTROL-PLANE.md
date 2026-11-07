# Hard-Family Measurement Control Plane

## Purpose

The measurement control plane decides whether a target is allowed to enter the
measurement fabric and whether any resulting evidence can be treated as
comparable. The contract is generic; hard-family runners are the first live
consumers because they are the current bridge/analyzer proving surface.

It sits above the existing measurement-fabric network:

```text
runner -> control plane -> API lane -> bridge lease -> analyzer -> artifacts -> authority packet
```

This layer exists so broad baseline runs can finish with useful packets even
when a lane, bridge, analyzer, or dependency chain is not healthy.

## Benchmark Question

Can the hard-family runner classify lane and bridge admission before scheduling
analyze work, so every target becomes comparable success, diagnostic-only
evidence, blocked, quarantined, or dependency-blocked instead of hanging or
silently producing unusable evidence?

## Traffic-Light States

| Light | Meaning | Evidence status |
| --- | --- | --- |
| `green` | Safe to run and safe to compare if the target itself succeeds. | Comparable admission only; not semantic proof by itself. |
| `yellow` | Safe to run only for diagnostics. | Non-comparable baseline data. |
| `red` | Do not run this target. | Emit a reasoned non-comparable packet. |
| `quarantined` | Known-bad lane, bridge, or target path. | Do not schedule until cleared. |

## Bridge Admission And Lease Contract

V1 modeled one bridge candidate with existing identity and readiness packets.
Tier 3 now supports configured bridge candidates and routes the selected bridge
URL into the managed analyze request. This is still sequential: one selected
bridge per target, no parallel scheduling, and no exclusive distributed lease.

Minimum packet fields:

- `schema_version`
- `source` (`measurement_control_plane`)
- `target`
- `analysis_profile`
- `required_capabilities`
- `light`
- `status`
- `reason_code`
- `blocking_reasons`
- `safe_to_run`
- `safe_to_compare`
- `selected_bridge`
- `lease`
- `dependency_policy`
- `evidence_paths`
- `next_action`
- `created_at`

V1 reason codes:

- `green_lane_admitted`
- `diagnostic_only_lane`
- `no_green_bridge_available`
- `bridge_capability_mismatch`
- `bridge_readiness_unavailable`
- `bridge_lane_quarantined`
- `lane_identity_not_comparable`
- `bridge_stream_health_unproven`
- `bridge_recent_no_heartbeat_stall`
- `bridge_stream_health_degraded`
- `bridge_stream_health_coherent`
- `bridge_candidate_registry_selected_green`
- `bridge_candidate_registry_selected_yellow`
- `bridge_candidate_registry_no_runnable_candidate`
- `no_non_quarantined_bridge_available`
- `quarantine_scope_prevents_poisoning`
- `ready_for_bounded_hard01_baseline_attempt`
- `not_ready_control_plane_gap`
- `not_ready_lane_identity_gap`
- `not_ready_packet_terminalization_gap`
- `not_ready_dependency_blocking_gap`
- `not_ready_selected_bridge_routing_gap`

## Dependency Rule

Dependency-invalid targets must not run blindly.

If Target B depends on Target A, B may run only when A produced the required
comparable or explicitly allowed state. If A is `red`, `yellow`, or
`quarantined` for a required semantic dependency, B must close as
`dependency_blocked`.

Independent targets may continue so a baseline run can still produce partial
evidence.

## Tier Ladder

| Tier | Requirement | Current state |
| --- | --- | --- |
| Tier 0 | Control-plane traffic-light states, reason codes, and map ownership are documented. | established by `hard_family_measurement_control_plane_design_v1` |
| Tier 1 | A pure helper builds deterministic green/yellow/red/quarantined admission packets, hard-family runners passively emit suite and per-target packets, bridge-stream health is represented as a passive input, and bounded proof compares packet prediction against actual target outcome without changing scheduling behavior. | implemented through `measurement_control_plane_passive_observation_v1`, `measurement_control_plane_passive_bounded_proof_v1`, and `hard_family_control_plane_bridge_health_signal_v1`; bridge health no longer stays invisible behind green admission |
| Tier 2 | Hard-family runners enforce the packet before analyze: green may remain comparable if execution succeeds, yellow is diagnostic-only/non-comparable, and red/quarantined fail closed before `run_one`. | implemented by `hard_family_bridge_lease_and_health_gate_v1`; bounded proof pending |
| Tier 3 | Multiple bridge candidates can be discovered from configuration, selected or rejected by capability, identity, readiness, health, and quarantine state, and hard-family runners route the selected bridge into analyze. | helper-level candidate registry implemented by `measurement_control_plane_tier3_bridge_candidate_registry_v1`; single-candidate runner consumption implemented by `measurement_control_plane_tier3_runner_candidate_consumption_v1`; configured multi-bridge candidate discovery implemented by `measurement_control_plane_tier3_multi_bridge_candidate_discovery_v1`; request-scoped selected bridge routing implemented by `measurement_control_plane_tier3_runner_multi_bridge_selection_v1`; runtime parallel bridge scheduling remains planned |
| Tier 4 | Bridge/lane quarantine and bounded recovery selection prevent known-bad bridge or bridge-target-profile paths from being selected, preserve expired/cleared rows as visible context, and fail closed when no usable candidate remains. | implemented at configured quarantine/recovery selection level by `measurement_control_plane_tier4_bridge_quarantine_recovery_v1`; live multi-bridge recovery proof remains planned |
| Tier 5 | Hard-family readiness gate: the runner emits a machine-readable verdict that lane identity, Tier 2 enforcement, Tier 3 selected routing, Tier 4 quarantine/recovery, non-comparable packet terminalization, dependency blocking, and semantic-proof containment are sufficient for a bounded hard01 baseline attempt. | implemented by `measurement_control_plane_hard01_baseline_readiness_gate_v1`; first bounded baseline classification completed by `hard01_bounded_baseline_attempt_v1` and routed to `worker_startup_stall` without a hard01 maturity claim |

## Questions This Suite Can Answer

- whether a target was allowed to run before bridge/analyzer work started
- whether a lane was comparable, diagnostic-only, blocked, or quarantined
- whether required bridge capabilities and readiness were present
- whether downstream dependency blocking should apply
- whether a baseline run produced non-comparable data by policy instead of by crash

## Questions This Suite Cannot Answer

- whether S-00 through S-07 stage semantics are correct
- whether hard01 is semantically mature
- whether Ghidra recovered the right function schema
- whether bridge execution is correct after admission
- whether a compiled target should pass product-level expectations

## What The Next Suite In This Category Should Add

`hard_family_bridge_lease_and_health_gate_v1` promotes passive observation into
per-target enforcement. The suite-level packet remains context only; each
target packet decides whether the runner may call `run_one`, whether the result
is diagnostic-only, or whether the target must fail closed before analyze.

The bridge-health proof showed `reservation_stage` is now yellow
diagnostic-only through `bridge_recent_no_heartbeat_stall`, while targets with
unproven bridge-stream health use `bridge_stream_health_unproven`. Under Tier 2,
yellow targets may still run for diagnostics, but their run authority is forced
non-decision-bearing even if execution appears successful. Red and quarantined
targets emit non-comparable `measurement-terminalization.json`,
`run-authority.json`, and `run_result.json` without scheduling analyzer work.

If the newer `analyzer_launch_connection_reset` signal recurs under enforcement,
route that fallback separately rather than weakening the control-plane rule.
`measurement_control_plane_tier3_bridge_candidate_registry_v1` adds the first
pure candidate-registry helper so future runner work can choose a green bridge
over yellow/red/quarantined candidates instead of assuming one hardcoded bridge.
`measurement_control_plane_tier3_runner_candidate_consumption_v1` wires that
registry packet into hard01/hard02 through the configured local bridge as a
single candidate. This proves runner consumption of the registry shape without
claiming true multi-bridge scheduling.
`measurement_control_plane_tier3_multi_bridge_candidate_discovery_v1` adds a
pure configured-candidate discovery helper. It normalizes multiple bridge URLs
into reviewable candidate rows but does not contact bridges, schedule work, or
grant leases.

`measurement_control_plane_tier3_runner_multi_bridge_selection_v1` makes the
configured candidate selection real for hard01/hard02 by passing the selected
bridge URL through `run_one`, `ApiClient.analyze`, `/api/analyze`, and
`_call_gui_bridge`. The API accepts only local allowlisted bridge overrides, and
discovery bridge-authority packets record the effective selected bridge URL.
This is still not parallel execution; it is sequential request-scoped routing
only.

`measurement_control_plane_tier4_bridge_quarantine_recovery_v1` adds a
configured quarantine registry consumed by the same candidate registry. Active
quarantine rows can target one bridge, one bridge/target pair, or one
bridge/target/profile path. Matching active rows force the candidate to
`quarantined`; expired and cleared rows stay visible without blocking. This
protects hard-family runs from reusing known-bad bridge paths while avoiding
suite-wide poisoning of unrelated targets.

`measurement_control_plane_hard01_baseline_readiness_gate_v1` adds the Tier 5
readiness verdict. `ready_for_bounded_hard01_baseline_attempt` means the
measurement system is ready to attempt a bounded hard01 baseline, not that hard01
is semantically healthy. Not-ready verdicts route to the exact gap:
`not_ready_lane_identity_gap`, `not_ready_control_plane_gap`,
`not_ready_packet_terminalization_gap`, `not_ready_dependency_blocking_gap`, or
`not_ready_selected_bridge_routing_gap`.

`hard01_bounded_baseline_attempt_v1` is the first consumer of that readiness
verdict. It proved the control-plane contract was sufficient to classify the
baseline attempt: green `session_bootstrap` became comparable, yellow
`reservation_stage` stayed non-comparable, and downstream targets were
dependency-blocked. The active blocker after that run is analyzer-runtime
`worker_startup_stall`, not control-plane readiness.

## Claim Ceiling

This control plane proves admission classification only. It does not promote
enterprise survivability tiers, stage breakpoint rows, hard01 maturity, or
semantic pipeline correctness.
