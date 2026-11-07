# System Map

This map separates what must survive redesign from what may churn and what must warn us when unrelated surfaces break.

| System | Role | Durable contracts | Primary proof surfaces |
| --- | --- | --- | --- |
| Lane startup | Materializes API and bridge for a job-local lane. | Startup does not depend on prior jobs; `/api/lab/status` is valid; promotion-safe is true before suite execution. | `runtime/start-managed-lane.ps1`, startup artifacts, workflow startup steps. |
| Lane trust | Tier 1 proving precheck and canary. | Canary is self-contained, observe-only under validator ownership, and emits failure artifacts before packet absence becomes the only truth. | `runtime/validate-local-lane.ps1`, lane trust result artifacts, required-regression workflow. |
| Compiled analyze-only | Minimum Ghidra-first discovery floor for compiled proving. | Strict DLL path avoids quarantined analyzer sprawl; native and .NET compiled paths stay bounded. | analyze-only canary packet, discovery profile tests, strict DLL routing tests. |
| Checkpoint runners | Run one semantic checkpoint at a time. | Target selection preserves chain order, predecessor job ids, and checkpoint-local artifacts. | `run_spectrum_compiled_easy01.py`, `run_spectrum_compiled_medium01.py`, checkpoint artifacts. |
| Checkpoint aggregation | Rebuilds suite-level truth from checkpoint artifacts. | Aggregation is a standalone CI entrypoint and feeds canonical baseline comparison shape. | `aggregate_checkpoint_suite.py`, `tests/test_checkpointized_regression_ci.py`. |
| Baseline comparison | Decides compiled suite verdicts against pinned roots. | Pinned baseline registry remains canonical; comparison reasons are preserved. | `api/analysis/regression_gate_v1.py`, compiled ingest compare reports. |
| CI eligibility | Decides which changed paths trigger heavy regression. | Runtime and gate changes trigger heavy gates; governance-only floor files do not when changed alone; mixed changes still trigger heavy gates. | `ci_gate_eligibility.py`, `tests/test_regression_ci_eligibility.py`. |
| Runner topology | Maps jobs to runner labels, ports, roots, and artifacts. | Product baseline gate membership comes from `configs/regression/gate_v1.json`; local proving posture comes from `configs/regression/product_proving_posture.json`; checkpoint graphs remain diagnostic unless promoted by their owning contract. | workflow YAML, gate config, product proving posture, runner-label tests, startup artifacts. |
| Summary writers | Convert artifacts into operator-readable truth. | Summary and diagnostic entrypoints run standalone and expose first concrete failure before generic packet absence. | `write_ci_job_summary.py`, `write_checkpoint_job_summary.py`, `regression_ci_diagnostics.py`, summary tests and CLI smokes. |
| Change admission | Classifies implementation blast radius before expensive proving. | Registry is valid; changed paths map to systems; durable contracts, allowed churn, and meta-checks are reported. | `check_registry.json`, `change_admission_check.py`, `run_change_admission_floor.py`, Fast Checks artifacts. |
| Stage handoff packets | Owns S00/S01 packet evidence and setup-to-unlock handoff contracts. | Packet schemas stay machine-readable; downstream consumers keep required handoff fields; stage docs do not widen required runtime suites. | `api/pipeline/core/s00_s01_handoff.py`, `api/pipeline/core/types.py`, S00/S01 docs, `tests/test_s00_s01_handoff_packet.py`. |
| Session routes | Exposes session snapshots and handoff packet truth through API route surfaces. | Route-visible packet fields remain deterministic and cheap to verify without running heavy regression suites. | `api/routes/routes_session.py`, `tests/test_routes_session_snapshot_handoff_packet.py`, `tests/test_routes_session_report.py`. |
| Worker persistence | Persists invocable and worker evidence for route/session consumers. | Worker writeback remains durable, observable, and covered before suite gates. | `api/infra/worker.py`, `tests/test_worker_invocables_persistence.py`. |
| Agent governance | Owns Codex operating law, specialist dispatch doctrine, and campaign governance. | Governance stays auditable; governance-only changes remain fast-floor unless mixed with runtime changes. | `AGENTS.md`, `.agents/**`, `docs/architecture/agentic_ecosystem/**`, `scripts/audit_governance.py`. |

## Classification Rule

- `durable_contract`: should remain true across architecture churn unless the operator explicitly changes the contract.
- `allowed_to_churn`: implementation details or proof surfaces expected to move during redesign.
- `meta_check`: cheap guard that detects workflow, import, artifact, schema, or topology breakage before expensive regression proving.
