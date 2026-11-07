# Efficiency Activation Design Suite v1 Compiled Packet

## Purpose

This document compiles `efficiency_activation_design_suite_v1` into an exact
runnable benchmark packet.

It defines:

- the compiled fixture
- the exact package shape
- the pass-one and pass-two execution rules
- the machine-readable outputs
- the metrics packet the dynamic campaign may legally depend on

## Runnable Fixture

- fixture root:
  - [tests/fixtures/spectrum_efficiency_activation_suite](../../../tests/fixtures/spectrum_efficiency_activation_suite)
- suite id:
  - `spectrum_efficiency_activation_suite`
- case id:
  - `activation-v1`
- benchmark protocol:
  - [benchmark_protocol.json](../../../tests/fixtures/spectrum_efficiency_activation_suite/benchmark_protocol.json)
- runner entrypoint:
  - [run_spectrum_efficiency_activation.py](../../../scripts/runs/run_spectrum_efficiency_activation.py)

## Package Shape

The compiled package contains exactly 10 DLLs and exactly 30 callable
candidates.

Modules:

- `spectrum_session_bootstrap`
- `spectrum_reservation_stage`
- `spectrum_dispatch_preview`
- `spectrum_fee_quote`
- `spectrum_attestation_stage`
- `spectrum_invoice_sync`
- `spectrum_entitlement_sync`
- `spectrum_settlement_reconcile`
- `spectrum_audit_trace`
- `spectrum_replay_branch`

Each DLL exports exactly:

- 1 primary path export
- 2 helper or noise exports

## Pass Rules

### Pass One

Pass one may deeply probe only:

- `session_bootstrap`
- `reservation_stage`
- `dispatch_preview`
- `fee_quote`

Pass one must leave explicit visibility for:

- `attestation_stage`
- `invoice_sync`
- `entitlement_sync`
- `settlement_reconcile`

Pass one must not deeply probe the false-positive frontier:

- `audit_trace`
- `replay_branch`

### Pass Two

Pass two may expand only to:

- `attestation_stage`
- `invoice_sync`
- `entitlement_sync`
- `settlement_reconcile`

Pass two must reuse pass-one outputs rather than behaving like a cold restart.

## Required Output Artifacts

The runner must emit at least:

- `activation-plan-pass-one.json`
- `activation-plan-pass-two.json`
- `operator-useful-map.json`
- `pass-two-reuse-report.json`
- `efficiency-activation-report.json`

The runner also emits:

- `package-inventory.json`
- `efficiency-activation-summary.json`

## Required Metrics Packet

The final report must contain exactly these benchmark metrics:

- `time_to_useful_map`
- `surfaces_deeply_probed_pass_one`
- `surfaces_deeply_probed_pass_two`
- `deferred_surface_count`
- `reuse_success_rate`
- `wasted_deep_probe_count`

## Comparison Rules

Baseline and later reruns should compare:

- whether pass one stayed bounded
- whether deferred surfaces were explicit
- whether the false-positive frontier stayed unprobed
- whether pass two reused trusted first-pass outputs
- whether the late truth surface remained available
- whether the workflow economics metrics improved without expanding scope

## Dynamic Campaign Gate

This compiled packet is the prerequisite surface for:

- dynamic_campaigns/efficiency_activation_system_build_v1/CAMPAIGN.md

That campaign may now use this compiled suite as its proving surface.

## Questions This Suite Can Answer

- can the pipeline produce a useful first-pass operational map before probing
  the whole package
- can it bound pass one to the intended frontier
- can it preserve explicit deferment
- can pass two reuse pass-one outputs instead of restarting cold
- can selective deepening improve a medium-band workflow economically

## Questions This Suite Cannot Answer

- is the product efficient enough for `50 DLL / 1,000 function` estates
- does the same policy survive deep cross-DLL interwoven-state pressure
- does the same policy survive noisy archive realism
- what the best production model mix is at enterprise scale
- how the system behaves under concurrency or queue pressure

## What The Next Suite In This Category Should Add

- larger-package throughput pressure
- noisy package realism
- stronger iteration-policy pressure beyond two staged passes
- enterprise-scale cost and scheduling pressure
