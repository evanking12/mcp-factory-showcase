# Spectrum Efficiency Activation Suite - Build Instructions

## What this fixture is

`spectrum_efficiency_activation_suite` is the compiled runnable fixture for
`efficiency_activation_design_suite_v1`.

It is not a generic speed benchmark. It is a product-shaping compiled suite
that tests:

- bounded first-pass activation
- explicit deferment
- false-positive frontier visibility
- pass-two expansion
- pass-two reuse
- medium-band workflow economics

The fixture is intentionally Spectrum-medium derived rather than toy-simple.

## Current package shape

The compiled package contains exactly 10 DLLs:

- `spectrum_session_bootstrap.dll`
- `spectrum_reservation_stage.dll`
- `spectrum_dispatch_preview.dll`
- `spectrum_fee_quote.dll`
- `spectrum_attestation_stage.dll`
- `spectrum_invoice_sync.dll`
- `spectrum_entitlement_sync.dll`
- `spectrum_settlement_reconcile.dll`
- `spectrum_audit_trace.dll`
- `spectrum_replay_branch.dll`

Each DLL exports exactly 3 symbols, for 30 callable candidates total.

## Benchmark grouping

The suite protocol separates the package into:

- pass-one active frontier
- pass-one visible but deferred
- false-positive frontier
- pass-two expansion

See [benchmark_protocol.json](benchmark_protocol.json)
for the exact runnable grouping.

## Build

Preferred:

```powershell
powershell -ExecutionPolicy Bypass -File .\build-package.ps1
```

This script:

- locates an MSVC toolchain
- compiles all 10 DLLs into `bin/`
- mirrors them into the upload directory when available
- stages the package into `.tmp/fixture-packages/`
- copies the package, truth, and benchmark manifests into the staged package
- emits `campaign-request.json` and `attach-plan.json`
- zips the staged package

## Output locations

- built DLLs: `tests/fixtures/spectrum_efficiency_activation_suite/bin/`
- built objects: `tests/fixtures/spectrum_efficiency_activation_suite/.obj/`
- staged package: `.tmp/fixture-packages/spectrum-efficiency-activation-suite/`
- zipped package: `.tmp/fixture-packages/spectrum-efficiency-activation-suite.zip`

## Design notes

This fixture deliberately encodes:

- a meaningful pass-one frontier
- delayed attestation reuse
- a late settlement truth surface
- one rich-looking but lower-value false-positive frontier

The binaries are meant to be statically meaningful and operationally staged,
not merely loadable.
