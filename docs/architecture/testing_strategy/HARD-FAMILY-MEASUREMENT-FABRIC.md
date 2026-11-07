# Hard-Family Measurement Fabric

## Purpose

This strategy layer owns the measurement network that makes hard-family runs
trustworthy enough to interpret:

`runner -> control plane -> API lane -> bridge lease -> analyzer -> artifacts -> authority packet`

Stage breakpoint tiers answer whether S-00 through S-07 do their local jobs.
Enterprise survivability answers whether a hard-shaped run can fail closed with
useful packets. The measurement fabric answers whether the software network
that produces those packets is itself observable, attributable, and comparable.
The traffic-light admission contract lives in
[`HARD-FAMILY-MEASUREMENT-CONTROL-PLANE.md`](HARD-FAMILY-MEASUREMENT-CONTROL-PLANE.md).
Compiled-suite green-label claim ceilings live in
[`COMPILED-SUITE-GREEN-CONTRACT.md`](COMPILED-SUITE-GREEN-CONTRACT.md);
measurement-fabric green evidence is not product-green unless the compiled
enterprise route also proves Ghidra-backed discovery and semantic/product
evidence. Compiled-suite product-green requires Ghidra-backed route authority
before any hard-family or Medium01 result may be read as product proof.

Control-plane campaign lineage stays explicit for drift checks:
`measurement_control_plane_passive_observation_v1`,
`measurement_control_plane_passive_bounded_proof_v1`,
`hard_family_control_plane_bridge_health_signal_v1`,
`hard_family_bridge_lease_and_health_gate_v1`,
`measurement_control_plane_tier3_bridge_candidate_registry_v1`,
`measurement_control_plane_tier3_runner_candidate_consumption_v1`,
`measurement_control_plane_tier3_multi_bridge_candidate_discovery_v1`,
`measurement_control_plane_tier3_runner_multi_bridge_selection_v1`,
`measurement_control_plane_tier4_bridge_quarantine_recovery_v1`,
`measurement_control_plane_hard01_baseline_readiness_gate_v1`,
`hard01_bounded_baseline_attempt_v1`, and
`reservation_stage_discovery_child_runtime_no_output_v1`,
`reservation_stage_post_progress_10_control_stall_v1`, and
`hard_family_post_explore_artifact_fetch_fail_closed_v1`, and
`reservation_stage_ghidra_first_discovery_routing_v1`.
`compiled_suite_product_green_contract_v1` now governs the vocabulary around
compatibility_green, measurement_green, route_green, semantic_green, and
product_green.
Canonical control-plane signal anchors include
`control_plane_green_but_bridge_stalled`, `bridge_recent_no_heartbeat_stall`,
`bridge_stream_health_unproven`, `analyzer_launch_connection_reset`,
`control_plane_yellow_diagnostic_enforced`, `no_non_quarantined_bridge_available`,
`quarantine_scope_prevents_poisoning`, and
`ready_for_bounded_hard01_baseline_attempt`,
`post_explore_verdict_fetch_connection_reset`,
`post_explore_verdict_fetch_failed`, and
`post_explore_findings_fetch_failed`.

## Benchmark Question

When a hard-shaped target cannot produce semantic evidence, can the measurement
network name the exact boundary that failed, preserve durable evidence paths,
and route the signal to the next owned campaign without polluting stage-tier
claims?

## Inventory Dashboard

| Category | Count | Current state | Next gap |
| --- | ---: | --- | --- |
| Measurement-fabric breakpoint families | 10 | Tier 0 inventory exists with covered guards through control-plane readiness, Ghidra-first route authority, S-07 closeout, and Hard03 standing-baseline terminalization; latest Hard03 work proved invoice-sync wait authority, Prompts 01-04 locally covered managed S-07 closeout through terminal status, Prompt 11 covered Hard03-runner pre-target API recovery, Prompt 16 recovered target-local fee_quote authority completion, Prompt 19 made the Prompt 18 strict-local preflight failure artifact-backed, Prompt 20 recovered API admission locally, Prompt 23 classified reservation-stage false-done authority completion, and Prompt 24 recovered reservation_stage authority completion target-locally | run a bounded reopen gate before any new full Hard03 spend |
| Covered guards | 4 | lane identity comparability, runner terminalization, dependency blocking, and failure-signal routing have durable guard evidence | keep guards synchronized with run-authority and signal-map changes |
| Analyzer/discovery rows | 5 | discovery output, Ghidra-first routing, subprocess control, bridge stream, and output persistence are mapped; Hard03 target-local managed replay recovered parent wait-return through `invoice_sync` and Prompt 16 recovered `fee_quote` authority completion | preserve wait-return and authority-completion rows as fallback while reopening Hard03 safely |
| Hard-family semantic readiness | 3 | Hard01 is defended product-green, Hard02 is comparable survivability finish-line, and Hard03 has local managed S-07 closeout authority, Hard03-runner pre-target API recovery, target-local `fee_quote` authority completion, and target-local `reservation_stage` authority completion after Prompt 24 | run a bounded reopen gate before reading Hard03 as unsupported-target quarantine evidence |
| Measurement control-plane admission | 1 | Tier 2 enforcement, Tier 3 selected bridge routing, Tier 4 configured quarantine/recovery selection, and Tier 5 hard01 readiness verdict are implemented; `bridge_stream_health_unproven` and `bridge_recent_no_heartbeat_stall` remain non-comparable when they appear | runtime parallel scheduling and live multi-bridge recovery remain future gaps |
| Compiled-suite green contract | 1 | product-green claims are frozen unless Ghidra-backed route authority and decision-bearing product evidence exist | prove the smallest compiled/no-source Ghidra-backed product route |

## Tier Ladder

| Tier | Requirement | Current state |
| --- | --- | --- |
| Tier 0 | Families mapped with owner, current state, claim ceiling, and next fixture or harness shape. | complete for v1 |
| Tier 1 | One measurement-fabric failure closes with a precise durable packet instead of silence, broad timeout, or crash. | covered by prior terminalization/analyzer authority evidence |
| Tier 2 | One boundary distinguishes multiple failure modes without collapsing them into generic hard01 failure. | partial: analyzer authority and bridge-stall classifiers exist |
| Tier 3 | Multiple hard-shaped targets exercise mixed fabric paths and all produce comparable or non-comparable authority packets. | implemented across Hard02 finish-line and Hard03 standing-baseline packets, but not all downstream challenge families are unlocked |
| Tier 4 | Recovery/state pressure proves fabric state survives failed branches, restarts, retries, and quarantines. | candidate: parent/child analyzer-runtime boundedness now holds target-by-target through `invoice_sync`; S-07 managed closeout is locally green for fresh runs; Prompt 11 covers Hard03-runner pre-target API recovery; Prompt 16 covers target-local `fee_quote` authority completion; Prompt 20 covers API admission locally; Prompt 24 covers target-local `reservation_stage` authority completion, but full Hard03 still needs a fresh gate and confirmation |
| Tier 5 | Hard-family readiness: hard-family suites can be considered for bounded baseline or promotion attempts because the measurement fabric can prove readiness or route the exact not-ready gap. | Hard01 is promoted product-green and Hard02 has comparable finish-line evidence; Hard03 is not ready until a verification gate authorizes and a reviewed full-run result exists |

## Measurement-Fabric Families

| Family | Weakness variable | Current state | Target tier | Owner | Next fixture or harness shape | Claim ceiling |
| --- | --- | --- | --- | --- | --- | --- |
| lane identity comparability | successful target comes from stale runner/API/bridge identity | `covered_guard` | Tier 3 | runner/API/bridge identity | bounded hard01 with managed restart and exact local SHA parity | identity trust only; no semantic hard01 maturity |
| runner terminalization | analyze/execution failure aborts without packet | `covered_guard` | Tier 3 | hard-family runner | one non-comparable target plus final suite packet | fail-closed packet production only |
| dependency blocking | successor target runs after required predecessor is non-comparable | `covered_guard` | Tier 3 | hard-family dependency graph | A comparable, B non-comparable, C dependency-blocked chain | downstream skip honesty only |
| discovery output authority | analyzer produces status but no durable discovery artifacts | classifier evidence exists | Tier 3 | analyzer/discovery producer | producer-side diagnostics over discoverable DLL with expected exports | discovery-output classification only |
| Ghidra-first discovery routing | hard-family `strict_dll` can become comparable through PE-only discovery before Ghidra-backed evidence is proven | `covered_guard`: `reservation_stage_ghidra_first_discovery_routing_v1` adds `ghidra_required` route authority; focused tests block PE-only comparability and bounded proof reached bridge authority instead of PE cleanup | Tier 2 | discovery route policy / bridge-Ghidra authority | keep the guard; route latest proof to bridge/Ghidra runtime authority | Ghidra-first route authority only |
| discovery subprocess control | discovery child or nested subprocess receives interrupt | `covered_by_latest_confirmation`: Hard03 target-local replay promoted `child_python_startup_interrupt` to repair-routing authority, focused tests added Windows process-group isolation, and latest full confirmation reached `reservation_stage` with child runtime `bootstrap_main_returned` instead of startup interrupt | Tier 2 | discovery subprocess orchestration | keep subprocess interrupt diagnostics as fallback while repairing parent wait-return authority | subprocess-interrupt authority only |
| bridge analyzer stream | API reaches bridge/analyzer boundary but stream never yields trustworthy result | `known_signal`: bridge-stream health and no-heartbeat stalls are mapped fallback/current-run authority rows, but latest Hard03 proof stopped before bridge attempt | Tier 3 | API-to-bridge stream / Ghidra runtime authority | bounded bridge/Ghidra request proof only after analyzer runtime reaches bridge | bridge/analyzer stream classification only |
| Ghidra/static analyzer boundedness | Analyzer progress stalls before comparable discovery output and before owner separation is clear | `covered_through_invoice_sync`: managed-lane target-local replay has covered parent wait-return, returncode observation, and output scan for all reached Hard03 analyzer targets through `invoice_sync`; Prompt 24 added target-local `reservation_stage` authority-completion recovery | Tier 4 candidate | API worker startup / analyzer-runtime diagnostic return path | preserve as fallback; active work moved to a Hard03 reopen gate | analyzer boundedness only |
| runner terminalization / API lane health | Runner loses API access while collecting terminal artifacts after a target reports done | `covered_guard`; verdict/finding fetch failures now write non-comparable post-explore artifact-fetch authority in focused tests, and bounded proof reached `reservation_stage` without a post-explore crash | Tier 2 | runner post-explore artifact retrieval | keep the guard; route current work to the latest `reservation_stage` child interrupt signal | runner terminalization authority only |
| output persistence | analyzer result exists but expected files are missing or misplaced | known classifier row | Tier 2 | artifact persistence path | output path mismatch harness with expected and actual file lists | persistence classification only |
| failure signal routing | raw logs are interpreted before becoming routable keys | `covered_guard` | Tier 3 | strategy/governance | signal-map governance check plus campaign closeout writeback | routing governance only |
| measurement control-plane admission | target scheduling happens before lane/bridge admission is classified | Tier 5 readiness gate is implemented for hard01 and the first bounded baseline attempt used it; green `session_bootstrap` became comparable while yellow `reservation_stage` stayed diagnostic-only/non-comparable | Tier 5 | runner/control-plane/bridge lane | keep admission evidence in baseline attempts while the analyzer-runtime owner is repaired | admission, candidate-selection, quarantine/recovery, and readiness mechanics only; no semantic proof |
| compiled-suite green contract | old green labels imply product proof without route authority | `covered_guard`: `compiled_suite_product_green_contract_v1` defines compatibility, measurement, route, semantic, and product green; historical Medium01 green remains compatibility/regression evidence unless promoted; route-authority harvesting recognizes Ghidra-backed saved-session evidence and `medium01_product_green_completion_stability_v1` completed two canonical-entrypoint Medium01 product-green runs | Tier 1 | testing-strategy governance / baseline taxonomy | run `medium01_product_green_baseline_promotion_v1` before rebasing active Medium01 Gate V1 truth | green-label contract reset and product-run completion/stability only; no baseline promotion yet |

## Latest Hard03 Measurement-Fabric Branch

Prompt 35 spent the Prompt 34-authorized ninth Hard03 attempt and reached
target execution. `session_bootstrap` completed with decision-bearing
authority, then `reservation_stage/analyze` failed closed when the `/api/analyze`
client request timed out before analyzer runtime entry, bridge attempt, Ghidra
entry, child launch, or discovery output. Prompt 36 proved the existing run
artifacts were missing `analyzer-runtime-authority`, so the classifier could
only fail closed on incomplete inputs.

Prompt 37 repaired only that authority gap. Top-level measurement
terminalization stays `analyzer_error`, while the analyzer-runtime packet
records `reason_code=analyze_api_read_timeout` and
`owner=api_analyze_launch`. The classifier now routes the sharp signal to
`reservation_stage_analyze_api_read_timeout_before_runtime_entry`.

Prompt 38 repaired only the `/api/analyze` upload/admission boundary by
bounding blob upload latency and falling back to direct-thread processing when
upload does not return before the configured timeout. The active branch is
`hard03_confirmation_reopen_gate_after_api_analyze_upload_timeout_repair`.
This is still measurement-fabric repair only; it does not reach unsupported
target quarantine semantics or lift Hard03.

Prompt 40 spent the Prompt 39-authorized tenth full attempt and reproduced
`reservation_stage_analyze_api_read_timeout_before_runtime_entry` with complete
analyzer-runtime authority. Prompt 41 repaired the next route-level
observability risk by routing upload-investigation diagnostic event writes
through a single bounded queue and serializing the shared JSON-list append
helper inside the API process. The active branch is now
`hard03_confirmation_reopen_gate_after_api_analyze_route_event_queue_repair`.
This remains measurement-fabric repair only and requires a fresh reopen gate
before any further full-suite spend.

## Current Active Route

```text
hard03_standing_baseline_observed
-> reservation_stage/analyzer_timeout
-> child_wrapper_wait_return_missing
-> hard03_child_wrapper_wait_return_authority_v1
-> discovery_empty
-> diagnostic child_python_startup_interrupt subreason
-> child_python_startup_interrupt branch-steering repair authority
-> hard03_child_python_startup_interrupt_repair_v1
-> full Hard03 confirmation blocked upstream at session_bootstrap/s07_emit_contract_artifacts_no_close
-> hard03_session_bootstrap_s07_contract_artifact_closeout_v1
-> session_bootstrap comparable
-> reservation_stage/analyzer_timeout
-> child_wrapper_wait_return_missing
-> target-local live discovery recovers parent wait
-> full managed Hard03 still reports child_wrapper_wait_return_missing
-> managed_lane_wait_recovery_mismatch
-> managed-lane target-local replay recovers reservation_stage wait authority
-> full Hard03 confirmation reaches dispatch_preview
-> dispatch_preview/analyzer_timeout
-> child_wrapper_wait_return_missing
-> dispatch_preview managed-lane replay recovers wait authority
-> full Hard03 confirmation reaches fee_quote
-> fee_quote/analyzer_timeout
-> child_wrapper_wait_return_missing
-> fee_quote managed-lane replay recovers wait authority
-> full Hard03 confirmation reaches attestation_stage
-> attestation_stage/analyzer_timeout
-> child_wrapper_wait_return_missing
-> attestation_stage managed-lane replay recovers wait authority
-> full Hard03 confirmation reaches invoice_sync
-> invoice_sync/analyzer_timeout
-> child_wrapper_wait_return_missing
-> invoice_sync managed-lane replay recovers wait authority
-> full Hard03 confirmation reaches invoice_sync S-07 finalize
-> runner_observed_nonterminal_timeout
-> s07_emit_contract_artifacts_no_close
-> managed closeout classifier at fee_quote
-> s07_checkpoint_closeout_missing
-> Prompt 02 target-local checkpoint-save authority proof
-> s07_macro_verdict_persist_missing
-> Prompt 03 target-local macro verdict persistence authority proof
-> s07_terminal_status_closeout_missing
-> Prompt 04 target-local terminal status authority proof
-> Prompt 05 lane-trust reopen gate
-> Prompt 06 pre-target API identity failure
-> Prompt 07 current-checkout API identity refresh
-> Prompt 08 second-confirmation reopen gate
-> Prompt 09 pre-target API identity failure
-> api_identity_not_durable_between_prompt08_reopen_gate_and_prompt09_runner_start
-> Prompt 10 bounded managed API durability classifier
-> managed_api_process_hang_after_fresh_gate
-> Prompt 11 Hard03-runner pre-target API recovery
-> Prompt 12 third-confirmation reopen gate
-> Prompt 13 third confirmation diagnostic result
-> fee_quote_analyze_analyzer_timeout_non_authoritative
-> Prompt 14 target-local fee_quote replay
-> non_comparable_analyzer_runtime_stall
-> Prompt 15 analyzer-runtime boundary classifier
-> fee_quote_false_done_status_without_authority_completion
-> Prompt 16 target-local authority-completion recovery
-> hard03_confirmation_reopen_gate_after_fee_quote_authority
-> Prompt 18 one authorized fourth confirmation attempt
-> api_local_lane_admission_unavailable
-> Prompt 19 strict-local-preflight authority packet
-> Prompt 20 pre-target API admission authority
-> hard03_confirmation_reopen_gate_after_api_admission_authority
-> Prompt 21 fifth-confirmation reopen gate
-> Prompt 22 fifth confirmation reaches target execution
-> reservation_stage_analyze_launch_api_timeout_non_authoritative
-> Prompt 23 reservation_stage false-done authority classification
-> Prompt 24 target-local reservation_stage authority completion recovery
-> hard03_confirmation_reopen_gate_after_reservation_stage_authority
```

This active route means Hard03 is not yet exercising its intended downstream
unsupported-target quarantine semantics. The latest active blocker is the
seventh-confirmation reopen gate after bounded pre-target API admission timeout
repair. The earlier S-07 target-local replay proved contract artifacts
could be emitted, but source evidence lacked the
durable `s07_finalize` checkpoint. The S-07 closeout repair added bounded
checkpoint-save authority and the follow-up full Hard03 confirmation moved
`01-session_bootstrap` to comparable `ok`.

`hard03_discovery_empty_producer_authority_v1` added that target-local
preservation step without promoting the subreason. Replay root
`.tmp/hard03-discovery-empty-producer-authority-v1/reservation-stage-01`
preserves `child_python_startup_interrupt` and
`child_bootstrap_entry_missing`, but `safe_to_steer_next_prompt=false` keeps the
producer subreason diagnostic-only. The active branch-steering blocker remains
`discovery_empty`.

`hard03_child_python_startup_interrupt_decision_authority_v1` tightened that
distinction: `discovery_empty` remains the parent suite blocker, but
`child_python_startup_interrupt` is now the active branch-steering repair
signal under measurement fabric / discovery subprocess control. The proof is
target-local only at
`.tmp/hard03-child-python-startup-interrupt-decision-authority-v1/reservation-stage-01`
and carries no product-green, comparable, or baseline-promotion authority.

`hard03_child_python_startup_interrupt_repair_v1` added Windows discovery-child
process-group isolation and passed focused runtime tests. Its first required
full confirmation stopped earlier at `01-session_bootstrap` with parent
`runner_observed_nonterminal_timeout` and sharp S-07 signal
`s07_emit_contract_artifacts_no_close`, so the next route became S-07
contract-artifact closeout before any downstream quarantine semantics.

`hard03_session_bootstrap_s07_contract_artifact_closeout_v1` repaired the
S-07 closeout seam enough for full Hard03 confirmation to pass
`session_bootstrap`. It then exposed suite-level
`reservation_stage/analyzer_timeout`, sharpened by target-local replay to
`child_wrapper_wait_return_missing`.

Historical keys such as `bridge_stream_no_heartbeat`,
`ghidra_required_not_entered`, `child_pe_export_close_keyboard_interrupt`,
`child_wrapper_wait_return_missing`, and `progress_10_status_persist_stall`
remain mapped fallback signals. Latest proof wins: do not route Hard03 to
bridge/Ghidra runtime or unsupported-target quarantine until discovery child
completion can produce durable parent wait-return and output-scan evidence.
Treat `child_wrapper_wait_return_missing` as the active branch-steering repair
signal only; do not treat it as product proof or comparable semantic evidence.

`hard03_reservation_stage_child_wrapper_wait_return_repair_v1` added a
target-local live discovery diagnostic and repaired two local seams: bridge
empty-return shape and communicate-first wait recovery. The live diagnostic
proved current-code parent wait-return, returncode observation, and output scan
for the Hard03 reservation DLL, then stopped downstream at
`ghidra_bridge_unavailable` because the diagnostic lacks managed bridge
context. Two full managed Hard03 confirmations still stopped at
`child_wrapper_wait_return_missing`. Latest-proof-wins therefore keeps the
parent blocker active but records diagnostic `managed_lane_wait_recovery_mismatch`
as the next classification target. Do not spend another full Hard03 rerun until
the managed-lane recovery mismatch has a target-local proof.

`hard03_managed_lane_wait_recovery_mismatch_v1` added that managed-lane
target-local proof and forced a current-run cache bypass through the normal
`/api/analyze` form path. The managed replay recovered `reservation_stage`
parent wait-return, returncode observation, and output-scan authority, and the
follow-up full Hard03 confirmation moved past `reservation_stage`.

`hard03_dispatch_preview_child_wrapper_wait_return_authority_v1` generalized
that replay surface to `dispatch_preview`. The target-local replay recovered
`dispatch_preview` wait-return, returncode observation, and output-scan
authority, and the follow-up full Hard03 confirmation moved past
`dispatch_preview`. The active blocker is now `fee_quote/analyzer_timeout`,
again sharpened to `child_wrapper_wait_return_missing`. This is still a
target-specific lift, not a family-tier lift: the invariant held for two
Hard03 targets but not yet across the suite. The next proof should target-local
replay `fee_quote` from the confirmed dispatch boundary before another full
Hard03 rerun.

`hard03_fee_quote_child_wrapper_wait_return_authority_v1` then reused that
managed-lane replay surface for `fee_quote`. The target-local replay recovered
`fee_quote` wait-return, returncode observation, and output-scan authority, and
the follow-up full Hard03 confirmation moved past `fee_quote`. The active
blocker is now `attestation_stage/analyzer_timeout`, again sharpened to
`child_wrapper_wait_return_missing`. This is still a target-specific lift, not
a family-tier lift: the invariant held for three Hard03 targets but not yet
across the suite. The next proof should target-local replay
`attestation_stage` from the confirmed fee-quote boundary before another full
Hard03 rerun.

`hard03_attestation_stage_child_wrapper_wait_return_authority_v1` then reused
that managed-lane replay surface for `attestation_stage`. The target-local
replay recovered `attestation_stage` wait-return, returncode observation, and
output-scan authority, and the follow-up full Hard03 confirmation moved past
`attestation_stage`. The active blocker is now
`invoice_sync/analyzer_timeout`, again sharpened to
`child_wrapper_wait_return_missing`. This is still a target-specific lift, not
a family-tier lift: the invariant held for four Hard03 targets but not yet
across the suite. The next proof should target-local replay `invoice_sync` from
the confirmed attestation boundary before another full Hard03 rerun.

`hard03_invoice_sync_child_wrapper_wait_return_authority_v1` then reused that
managed-lane replay surface for `invoice_sync`. The target-local replay
recovered `invoice_sync` wait-return, returncode observation, and output-scan
authority, and the follow-up full Hard03 confirmation no longer failed on
`child_wrapper_wait_return_missing`. It then stopped at `invoice_sync/s07_finalize`
with parent `runner_observed_nonterminal_timeout` and sharp signal
`s07_emit_contract_artifacts_no_close`.

`hard03_invoice_sync_s07_contract_artifact_closeout_v1` split that S-07 blocker
with replay and focused closeout tests. The campaign added child-return recovery
when required contract artifacts are already present and avoided nonessential
stage-snapshot expansion during final S-07 checkpoint save. The mapped full
Hard03 confirmation still stopped in the same S-07 closeout family at
`fee_quote`, and the follow-up readiness attempt also failed before target
execution in S-07 closeout. This kept the family active and blocked any
downstream quarantine claim.

`hard03_s07_closeout_recovery_lane_authority_v1` then added a read-only
managed closeout classifier. Prompt 01 found that `fee_quote` job `ccc40dd5`
has required contract artifacts, but lacks `s07_finalize` checkpoint-save
return authority or worker-close trace evidence. Prompt 02 added verified
checkpoint-save authority for fresh runs: the runner now verifies
`checkpoints/s07_finalize.json`, emits
`checkpoints/s07_finalize_save_authority.json`, and only then records
checkpoint-save return. A fresh target-local helper proof moved
`checkpoint_save_return` to `returned` and exposed
`s07_macro_verdict_persist_missing` as the next ordered closeout boundary.
Prompt 03 then added verified macro verdict persistence authority:
the runner verifies `macro_verdict.json`, emits
`macro_verdict_persist_authority.json` for returned/failed/timeout outcomes,
and the classifier consumes that packet. A fresh target-local helper proof
moved `macro_verdict_persist` to `persisted` and exposed
`s07_terminal_status_closeout_missing` as the next ordered closeout boundary.
Prompt 04 added verified terminal status persistence authority: the runner
verifies terminal `status.json`, emits `final_status_persist_authority.json`
for returned/failed/timeout outcomes, and includes predecessor macro-verdict
authority fields. A fresh target-local helper proof moved
`terminal_status_persist` to `terminal` and `sharp_signal` to
`s07_managed_closeout_green`, while preserving `safe_to_compare=false`.
The frozen `ccc40dd5` proof root remains historical closeout evidence because
it predates the repairs; this is still no Hard03 product-green, Gate V1, full
confirmation, or tier-lift evidence. Prompt 05 passed the lane-trust reopen
gate and authorized exactly one full Hard03 confirmation, but Prompt 06 failed
before target execution at API OpenAPI identity resolution. Prompt 07 restored
the current-checkout lane/API identity surface. Prompt 08 authorized exactly
one immediate second full Hard03 confirmation, but Prompt 09 repeated the
pre-target API OpenAPI identity failure before target execution. The active
branch moved to `managed_api_process_hang_after_fresh_gate`: Prompt 10 showed
that immediate fresh-lane API identity can pass, then bounded runner-style
pre-target handoff can leave the API process listening on `8201` while
identity, readiness, and OpenAPI probes time out. Prompt 11 added
Hard03-runner-scoped pre-target API recovery and fail-closed authority before
target execution. Prompt 12 then passed lane-trust and pre-target API authority
checks and authorized exactly one third confirmation spend. Prompt 13 spent
that attempt and stopped at `fee_quote/analyze` with `analyzer_timeout`.
Prompt 14 then stayed target-local: it recovered replay pre-target API identity
and parent/child wait-return authority for `fee_quote`, but the replay still
failed closed with `non_comparable_analyzer_runtime_stall`. The active branch
was analyzer/bridge runtime isolation, not a product claim or full-run
authorization. Prompt 15 added a read-only boundary classifier and sharpened the
operator-decision contradiction to
`fee_quote_false_done_status_without_authority_completion`: public status says
done while terminal authority stays timeout/non-authoritative with missing
verdict, invalid run, and incomplete session capture.

Prompt 16 repaired that reconciliation seam for fresh target-local proof. The
runner now emits `authority-completion-reconciliation.json` for both
measurement-terminalized false-done cases and successful terminal-authority
completion paths. Fresh `fee_quote` replay
`.tmp/hard03-s07-closeout-recovery-lane-authority-v1/prompt-16/fee-quote-managed-lane-replay-03`
finished with decision-bearing run authority and classifier output
`authority_completion_reconciled`. This is still target-local evidence; it
routes the next branch to `hard03_confirmation_reopen_gate_after_fee_quote_authority`,
not directly to a full Hard03 spend or tier lift.

Prompt 17 authorized exactly one fourth Hard03 confirmation attempt. Prompt 18
spent that attempt and failed before target execution in strict local lane
preflight: API identity resolved, but API local-lane admission was unavailable.
Prompt 19 added `strict-local-preflight-authority.json` on pass/fail and proved
the integrated runner path emits `api_local_lane_admission_unavailable` with
`target_execution_invoked=false`, `safe_to_compare=false`, and
`product_green_claimed=false`.

Prompt 20 repaired that admission availability seam for bounded pre-target
proof by moving blocking API readiness/admission route handlers onto synchronous
FastAPI execution, preserving the route contract while avoiding event-loop
blocking from dependency probes. After managed API relaunch, API identity,
readiness, API admission, bridge admission, and strict local preflight all
passed with `target_execution_invoked=false`. This moves the branch to a
reopen gate; it does not authorize a full Hard03 attempt by itself.

Prompt 21 passed that reopen gate and authorized exactly one immediate fifth
full Hard03 attempt. Prompt 22 spent it. The run reached target execution and
completed `session_bootstrap`, but `reservation_stage/analyze` failed closed
with API read timeout on `127.0.0.1:8201` before Ghidra entry, bridge attempt,
or discovery output. Prompt 23 sharpened that failure to
`reservation_stage_false_done_status_without_authority_completion`: public
status could report done with selected invocables while terminal authority
remained timeout/non-authoritative. Prompt 24 repaired that seam
target-locally by adding analyze-timeout recovery authority, target-aware
classifier signals, and a fresh replay that completed `reservation_stage` with
decision-bearing authority and `authority_completion_reconciled`. Prompt 25
authorized exactly one sixth Hard03 confirmation attempt. Prompt 26 spent that
attempt and failed before target execution: API identity passed, but strict
local API admission was unavailable. Prompt 27 repaired the pre-target
admission timeout seam by bounding the API model health probe and preserving
the contract that model reachability is diagnostic for strict local admission.
Fresh pre-target proof passed API identity, API admission, bridge admission,
and strict local preflight with `target_execution_invoked=false`.

Prompt 28 passed the seventh-confirmation reopen gate and authorized exactly
one seventh attempt. Prompt 29 spent it and failed before target analyze: the
post-restart readiness probe reported ready, but final lane readiness had
`api_readiness={}` and `api_readiness_unavailable`. Prompt 30 repaired only
that post-restart API readiness survival seam. The runner now emits
`post-restart-api-readiness-survival-authority.json`, may perform one managed
local API relaunch only after a ready post-restart probe and a recorded managed
restart, then reruns strict local preflight before target execution. Fresh
Prompt 30 proof recovered API readiness and preflight with
`target_execution_invoked=false`.

Prompt 31 reopened exactly one eighth confirmation attempt. Prompt 32 spent it
and failed before target execution at auto-detected local
`api_readiness_unavailable`. Proving review allowed only the narrow
fail-before-target meaning because the harness changed after the run. Prompt
33 repaired that managed-local pre-target identity recovery branch and
refreshed current-checkout API identity without target execution. The active
row is now the ninth-confirmation reopen gate, not S-07 closeout,
reservation-stage authority completion, unsupported-target quarantine
semantics, or product-green movement.

## Required Outputs

Measurement-fabric rows must preserve:

- canonical signal key
- owner boundary
- current tier or state
- safe-to-compare verdict
- durable evidence paths
- claim ceiling
- next recommended campaign

## Questions This Suite Can Answer

- Which measurement boundary owns a hard-family failure signal?
- Is a successful target comparable evidence or only operational output?
- Did a non-comparable target close with reviewable packets?
- Did a dependency-blocked target stop instead of manufacturing downstream evidence?
- Does a raw failure have a canonical key and next campaign?

## Questions This Suite Cannot Answer

- It cannot prove S-00 through S-07 stage semantics.
- It cannot prove enterprise survivability Tier 4 recovery pressure.
- It cannot make hard01 or hard02 semantically mature.
- It cannot replace compiled/product-shaped evidence when runtime behavior is the claim.

## What The Next Suite In This Category Should Add

`reservation_stage_child_wrapper_process_wait_stall_v1` installed additive
parent-side wait/returncode/output-scan breadcrumbs, but the latest bounded
Easy01 proof did not reproduce the wrapper-wait seam. Latest-proof-wins moved
the active route back to `ghidra_required_not_entered`: under
`ghidra_required=true`, `reservation_stage` emitted no discovery files, no
child diagnostics, and import/bootstrap `0xC000013A` stderr before any
Ghidra-backed route authority was entered. The next campaign in this category
should therefore inspect why the Ghidra-required route is not entered before
discovery terminalization, not continue to assume the bridge-stream boundary is
active. Older keys such as `post_progress_10_control_stall`,
`worker_startup_stall`, `child_nested_subprocess_interrupt`,
`child_import_bootstrap_interrupt`, `discovery_child_launch_missing`,
`discovery_child_popen_stall`, `discovery_child_popen_exception`,
`discovery_child_running_no_output`, `child_runtime_diagnostic_missing`,
`child_wrapper_wait_return_missing`, `child_returncode_observation_missing`,
`child_output_scan_missing`, `child_completed_no_output`,
`status_packet_missing_parent_closeout`, `child_wrapper_process_wait_stall`,
and `analyzer_launch_connection_reset` remain mapped fallback signals only. The
progress-10 fallback ladder still includes `progress_10_status_persist_stall`,
`progress_10_authority_emit_stall`, `progress_10_authority_return_marker_missing`,
`progress_30_persist_start_missing`, and `unknown_post_progress_10_control_stall`.
Historical campaign anchors include
`reservation_stage_analyzer_runtime_progress10_stall_v1`,
`reservation_stage_discovery_child_runtime_no_output_v1`, and
`reservation_stage_child_wrapper_process_wait_stall_v1`.
Live multi-bridge route proof and parallel scheduling remain future work.
