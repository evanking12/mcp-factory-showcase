# S-01 Trace / Surface Map

This is the operator map for S-01. It explains the files and artifacts that
matter for write-unlock work without pretending S-01 owns S-00 setup,
pipeline orchestration, or shared storage systems.

## Legend

| Marker | Meaning |
| --- | --- |
| `red / owned` | S-01 canonical implementation or S-01-owned live contract. |
| `yellow / dependency` | Required by S-01 but owned by a shared layer or adjacent stage. |
| `gray / upstream` | Runs before S-01 and feeds or invokes it. |
| `green / output` | Artifact, packet, or context surface emitted for later consumers. |

## Runtime Trace

| Step | Surface | Marker | Why S-01 cares |
| --- | --- | --- | --- |
| Pipeline runner invokes S-01 | `api/pipeline/runner.py` | yellow / dependency | Controls when S-01 runs after S-00. |
| S-00 handoff packet is available | `api/pipeline/core/s00_s01_handoff.py` | gray / upstream | Provides the admitted setup/static slice S-01 should read first. |
| S-01 entrypoint | `api/pipeline/s01_unlock/__init__.py` | red / owned | Owns the live unlock stage boundary and context mutation. |
| Write unlock probing | `api/pipeline/s01_unlock/write_unlock.py` | red / owned | Runs the write-unlock probe and records whether unlock is resolved or deferred. |
| Unlock helpers | `api/pipeline/s01_unlock/unlock_helpers.py` | red / owned | Supports unlock classification and probe mechanics. |
| S-02 consumer | `api/pipeline/s02_probe/__init__.py` | yellow / downstream dependency | Reads unlock state before broader probing. |

## Artifact Trace

| Artifact | Marker | Expected runtime home | Why it matters |
| --- | --- | --- | --- |
| `s01_handoff_packet.json` | gray / upstream | `local-data/artifacts/<job_id>/s01_handoff_packet.json` | S-00-owned packet S-01 admits before legacy fallback. |
| `write_unlock_probe.json` | green / output | `local-data/artifacts/<job_id>/write_unlock_probe.json` | S-01-owned unlock outcome and tested sequence. |
| `winning_init_sequence.json` | green / optional output | `local-data/artifacts/<job_id>/winning_init_sequence.json` | Concrete init sequence when write mode is discovered. |
| `code_reasoning_analysis.json` | green / optional output | `local-data/artifacts/<job_id>/code_reasoning_analysis.json` | LLM/code-reasoning support for unlock patterns. |

## Expected Homes

| Thing | Expected home |
| --- | --- |
| Live S-01 implementation | `api/pipeline/s01_unlock/` |
| S-01 artifact contract | `api/pipeline/s01_unlock/ARTIFACTS.md` |
| S-01 guarantees and fallback behavior | `api/pipeline/s01_unlock/LIVE-CONTRACT.md` |
| S-01 dependency map | `api/pipeline/s01_unlock/SYSTEMS.md` |
| S-01 trace and surface ownership | `api/pipeline/s01_unlock/TRACE.md` |
| S-00 handoff producer | `api/pipeline/s00_setup/` and `api/pipeline/core/s00_s01_handoff.py` |
| Runtime job artifacts | `local-data/artifacts/<job_id>/` |
