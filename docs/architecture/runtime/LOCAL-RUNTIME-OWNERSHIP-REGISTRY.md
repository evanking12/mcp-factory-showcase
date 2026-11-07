# Local Runtime Ownership Registry

This registry is the authoritative ownership map for the strict local operator path.

## `authoritative_active`

- `runtime/local-runtime-contract.json`
  Purpose: canonical local lane topology and runtime ownership contract.
  Trust: strong.
  May steer operator behavior: yes.
- `runtime/api/*`
  Purpose: API runtime home, start path, and check path.
  Trust: strong.
  May steer operator behavior: yes.
- `runtime/bridge/*`
  Purpose: bridge runtime home, start path, and check path.
  Trust: strong.
  May steer operator behavior: yes.
- `runtime/runners/proving-lane-canary/*`
  Purpose: canonical bounded proving runner for local lane trust.
  Trust: strong for bounded lane proof only.
  May steer operator behavior: yes.
- `runtime/validate-local-lane.ps1`
  Purpose: single bounded operator validator for the managed local lane.
  Trust: strong.
  May steer operator behavior: yes.
- `start.ps1`
  Purpose: canonical managed startup implementation for local API and bridge ownership.
  Trust: strong.
  May steer operator behavior: yes.
- `setup.ps1`
  Purpose: canonical strict-local setup validation and operator bootstrap.
  Trust: strong.
  May steer operator behavior: yes.
- `docs/architecture/runtime/LOCAL-RUNTIME-OWNERSHIP-REGISTRY.md`
  Purpose: explicit ownership map for runtime-related surfaces.
  Trust: strong.
  May steer operator behavior: yes.

## `active_pending_migration`

- `scripts/runs/run_spectrum_compiled_hard01.py`
  Purpose: compiled-suite proof surface now gated by strict-local admission.
  Trust: acceptable for authoritative compiled proof after live validation.
  May steer operator behavior: yes.
- `scripts/runs/run_spectrum_compiled_hard02.py`
  Purpose: harder compiled-suite proof surface now gated by strict-local admission.
  Trust: acceptable, but not the canonical proof surface for this tranche.
  May steer operator behavior: yes.
- `scripts/runs/run_spectrum_compiled_medium01.py`
  Purpose: active phase-1 stage-split-adjacent baseline workflow surface.
  Trust: acceptable once live validation is green.
  May steer operator behavior: yes.
- `scripts/stage_split_compare_phase1.py`
  Purpose: bounded phase-1 baseline/candidate comparison gate.
  Trust: acceptable; comparison-only surface, not a runner.
  May steer operator behavior: yes.
- `dashboard/main.py`
  Purpose: operator dashboard that still reflects runtime defaults in UI surfaces.
  Trust: acceptable after canonical loopback pinning.
  May steer operator behavior: yes.
- `configs/harness/tonight.json`
  Purpose: active overnight harness config example for local lane use.
  Trust: acceptable after canonical loopback pinning.
  May steer operator behavior: yes.

## `legacy_non_authoritative`

- `scripts/azure/*`
  Purpose: cloud-era storage and deployment helpers.
  Trust: legacy only.
  May steer operator behavior: no.
- `docs/architecture/_archive/oldstuff/*`
  Purpose: archived historical notes.
  Trust: legacy only.
  May steer operator behavior: no, unless a current authoritative doc explicitly references one.
- cloud-era deployment notes outside `runtime/*`
  Purpose: historical infra guidance for Azure-hosted operation.
  Trust: legacy unless a current runtime doc re-links it.
  May steer operator behavior: no.
- raw `/health`-only bridge reachability checks in inactive or historical surfaces
  Purpose: backward compatibility and legacy diagnostics.
  Trust: non-authoritative for strict local runtime.
  May steer operator behavior: no.
- `sessions/restart_local_services.ps1`
  Purpose: legacy wrapper retained only because historical prompts and notes still reference it.
  Trust: non-authoritative wrapper; defer to `start.ps1`.
  May steer operator behavior: no.
- `scripts/bridge/install-bridge-service.ps1`
  Purpose: implementation-level bridge service helper.
  Trust: specialist utility only.
  May steer operator behavior: no.
