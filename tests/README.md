# Test Inventory

> Executable regression inventory.
> The seam-level proving and regression home is
> [docs/architecture/testing_strategy/README.md](../docs/architecture/testing_strategy/README.md).

This directory is intentionally broad because it protects both pipeline
behavior and the measurement/capture surfaces around it. The tests should stay
explicitly categorized instead of being treated as a loose pile.

## Category Map

### Capture / Save-Session / Session Artifacts

- `test_capture.py`
- `test_capture_manifests.py`
- `test_collect_session_v2.py`
- `test_validation_report.py`
- `test_campaign_snapshot_structure.py`
- `test_checkpoint_stage_snapshots.py`

Purpose:
- verify local capture, snapshot manifests, checkpoint copies, and saved
  session structure

Why it matters:
- saved sessions are the debugging boundary for long runs and overnight loops

### Contract / Handoff / Cohesion Truth

- `test_contract_artifacts.py`
- `test_contract_compatibility.py`
- `test_handoff_contract_audit.py`
- `test_schema_handoff_audit.py`
- `test_transition_readiness.py`
- `test_flow_cohesion.py`
- `test_finding_status_ssot.py`

Purpose:
- protect contract-first stage and transition semantics

Why it matters:
- if these drift, later stage conclusions stop being trustworthy

### Checkpoint / Context / Evidence Systems

- `test_checkpoint_evidence.py`
- `test_checkpoint_stage_snapshots.py`
- `test_evidence_candidates_ghidra.py`
- `test_mc_evidence_consumption.py`
- `test_runner_seeded_findings.py`

Purpose:
- verify checkpoint boundaries, evidence ranking, seeded carry-forward, and
  stage-boundary evidence consumption

Why it matters:
- these are the core memory and reuse systems of the pipeline

### Campaign / Multi-DLL / Attribution

- `test_campaign_status_storage.py`
- `test_campaign_snapshot_structure.py`
- `test_campaign_attribution_report.py`
- `test_worker_invocables_persistence.py`
- `test_invocable_union.py`

Purpose:
- protect campaign identity, shared discovery, per-DLL persistence, and
  attribution surfaces

Why it matters:
- campaign scale multiplies bookkeeping bugs if these are weak

### Runner / Integration / Harness

- `test_explore_integration.py`
- `test_harness_cli.py`
- `test_run_targeted.py`
- `test_compare_runs.py`
- `test_verify_sync.py`
- `test_nightly_preflight.py`

Purpose:
- verify orchestration, command-line workflows, and run-cycle tooling

### Discovery / Static Analysis / Binary Handling

- `test_discovery_fallback.py`
- `test_static_analysis_direction_reclass.py`
- `test_ghidra_analyzer.py`
- `test_executor_dll_uint.py`
- `test_gui_bridge_upload_paths.py`
- `test_analyze_path_skip_cache.py`
- `test_synthesis_fallback.py`

Purpose:
- protect binary discovery, static hints, marshalling, and path handling

### Fixtures / Smoke / Misc

- `test_fixtures.py`
- `test_collector_epoch_and_ledger.py`
- `test_mcp_stdio.py`

Purpose:
- fixture integrity, ledger correlation, and optional environment-dependent
  smoke coverage

## Current High-Value Tests For MVP Work

These are especially important right now:

- `test_mc_evidence_consumption.py`
  - guards the generic candidate-ranking and evidence-consumption behavior that
    recently pushed `contoso_cs.dll` to `12/12`
- `test_campaign_attribution_report.py`
  - guards whether campaign gains are attributable rather than hand-wavy
- `test_checkpoint_stage_snapshots.py`
  - guards checkpoint granularity for quick iteration
- `test_campaign_snapshot_structure.py`
  - guards campaign save-session layout and capture fidelity

## Organization Rule Going Forward

Before adding a new test, decide which category it protects:

1. capture/session
2. contract/cohesion
3. checkpoint/context/evidence
4. campaign/attribution
5. runner/harness
6. discovery/static-analysis

If the category is unclear, the system being tested is probably unclear too.

## Near-Term Reorganization Policy

Do not move large numbers of existing tests just to create folder churn.
Prefer:

- an explicit inventory first
- stable naming by protected subsystem
- selective future subdirectories only when a category becomes large enough to
  justify the move

Right now the inventory is the important missing piece.
