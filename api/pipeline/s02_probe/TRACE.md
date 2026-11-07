# S-02 Trace / Surface Map

This is the operator map for S-02. It explains the files and artifacts that
matter for probing without making S-02 own discovery, setup, unlock, or final
documentation.

## Legend

| Marker | Meaning |
| --- | --- |
| `red / owned` | S-02 canonical implementation or S-02-owned live contract. |
| `yellow / dependency` | Required by S-02 but owned by a shared layer or adjacent stage. |
| `gray / upstream` | Runs before S-02 and feeds or invokes it. |
| `green / output` | Artifact, packet, or context surface emitted for later consumers. |

## Runtime Trace

| Step | Surface | Marker | Why S-02 cares |
| --- | --- | --- | --- |
| Pipeline runner invokes S-02 | `api/pipeline/runner.py` | yellow / dependency | Controls when probing starts after setup and unlock. |
| Setup context | `api/pipeline/s00_setup/` | gray / upstream | Supplies sentinels, vocab, static hints, and invocable context. |
| Unlock context | `api/pipeline/s01_unlock/` | gray / upstream | Determines whether write functions are safe or blocked. |
| S-02 compatibility parent | `api/pipeline/s02_probe/__init__.py` | red / owned | Preserves `run_s02` as the legacy full-stage entrypoint while dispatching S-02A/B/C. |
| S-02A probe ordering | `api/pipeline/s02_probe/probe_ordering.py` | red / owned | Owns `s02_probe_ordering` status/checkpoint attribution for curriculum and prerequisite planning. |
| Probe curriculum | `api/pipeline/s02_probe/curriculum.py` | red / owned | Orders probe attempts from available structural and setup evidence. |
| S-02B invocation execution | `api/pipeline/s02_probe/invocation_execution.py` | red / owned | Owns `s02_invocation_execution` status/checkpoint attribution around the probe loop. |
| Probe loop | `api/pipeline/s02_probe/probe_loop.py` | red / owned | Executes calls, captures arguments, returns, and observed behavior. |
| S-02C evidence capture | `api/pipeline/s02_probe/evidence_capture.py` | red / owned | Owns `s02_evidence_capture` status/checkpoint attribution for evidence persistence and boundary recalibration. |
| S-02 substage status | `api/pipeline/s02_probe/status.py` | red / owned | Emits runtime-visible S-02A/B/C status while preserving `s02_probe` as parent compatibility stage. |
| S-03 consumer | `api/pipeline/s03_reconcile/__init__.py` | yellow / downstream dependency | Reads probe evidence for deterministic correction and classification. |

## Artifact Trace

| Artifact | Marker | Expected runtime home | Why it matters |
| --- | --- | --- | --- |
| `explore_probe_log.json` | green / output | `local-data/artifacts/<job_id>/explore_probe_log.json` | Concrete call evidence produced by S-02. |
| `explore_config.json` | green / output | `local-data/artifacts/<job_id>/explore_config.json` | Runtime cap/profile settings for probe behavior. |
| `mcp_schema_t0.json` | green / output | `local-data/artifacts/<job_id>/mcp_schema_t0.json` | Pre-enrichment schema baseline for later comparison. |
| `prerequisite_state_machine.json` | green / output | `local-data/artifacts/<job_id>/prerequisite_state_machine.json` | S-02A ordering and prerequisite-state plan. |
| `evidence/stage-02a-probe-ordering/*` | green / output | session snapshot alias | Runtime-visible future home for S-02A artifacts. |
| `evidence/stage-02b-invocation-execution/*` | green / output | session snapshot alias | Runtime-visible future home for S-02B invocation context artifacts. |
| `evidence/stage-02c-evidence-capture/*` | green / output | session snapshot alias | Runtime-visible future home for S-02C persisted probe evidence. |

## Expected Homes

| Thing | Expected home |
| --- | --- |
| Live S-02 implementation | `api/pipeline/s02_probe/` |
| S-02 artifact contract | `api/pipeline/s02_probe/ARTIFACTS.md` |
| S-02 guarantees and caveats | `api/pipeline/s02_probe/LIVE-CONTRACT.md` |
| S-02 dependency map | `api/pipeline/s02_probe/SYSTEMS.md` |
| S-02 trace and surface ownership | `api/pipeline/s02_probe/TRACE.md` |
| Runtime job artifacts | `local-data/artifacts/<job_id>/` |
