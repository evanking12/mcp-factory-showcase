# S-00 Trace / Surface Map

This is the operator map for S-00. It explains the files and artifacts that
matter from DLL intake through the S-00 to S-01 handoff without pretending S-00
owns every upstream or shared layer.

## Legend

| Marker | Meaning |
| --- | --- |
| `red / owned` | S-00 canonical implementation or S-00-owned live contract. |
| `yellow / dependency` | Required by S-00 but owned by a shared layer. |
| `gray / upstream` | Runs before S-00 and feeds or invokes it. |
| `green / output` | Artifact, packet, or context surface emitted for later consumers. |

## Runtime Trace

| Step | Surface | Marker | Why S-00 cares |
| --- | --- | --- | --- |
| DLL intake by path | `api/routes/main.py` | gray / upstream | `/api/analyze-path` creates a job from an installed or local DLL path before S-00 exists. |
| DLL intake by upload | `api/routes/main.py` | gray / upstream | `/api/analyze` stores an uploaded DLL under `local-data/uploads/<job_id>/input.dll`. |
| Analysis worker | `api/infra/worker.py` | gray / upstream | Runs discovery and persists job status and invocable context before explore. |
| Discovery/Ghidra skeleton | `api/services/discovery.py` | gray / upstream | Produces the invocable skeleton that S-00 enriches. |
| Pipeline runner | `api/pipeline/runner.py` | yellow / dependency | Invokes `s00_setup_baseline`, then `s00_static_evidence`, then `s00_admission_handoff`, then S-01 while preserving `s00_setup` compatibility. S-00 does not own shared stage orchestration. |
| S-00 entrypoint | `api/pipeline/s00_setup/__init__.py` | red / owned | Preserves the live S-00 parent compatibility wrapper for setup baseline. |
| Setup baseline boundary | `api/pipeline/s00_setup/setup_baseline.py` | red / owned | S-00-owned runtime checkpoint boundary that establishes sentinel and vocab baseline before static evidence. |
| S-00 substage status surface | `api/pipeline/s00_setup/status.py` | red / owned | Emits runtime-visible `s00_setup_baseline`, `s00_static_evidence`, and `s00_admission_handoff` status while preserving `s00_setup` as parent compatibility stage. |
| Calibration/baseline truth seam | `api/pipeline/s00_setup/baseline_truth.py` | red / owned | S-00-owned seam for establishing the sentinel/error-code baseline before vocab and static extraction. |
| Sentinel calibration implementation | `api/pipeline/s00_setup/calibration.py` | red / owned | Current implementation that probes functions, resolves high-bit return codes, merges hint-provided error codes, and falls back to defaults. |
| Vocab/prior-hints seam | `api/pipeline/s00_setup/vocab_prior_hints.py` | red / owned | S-00-owned seam for seeding vocab and prior hints before static extraction. |
| Vocabulary seeding implementation | `api/pipeline/s00_setup/vocab_seed.py` | red / owned | Current implementation that builds `vocab.json` from signatures, hints, use cases, and prior context. |
| Static evidence boundary | `api/pipeline/s00_setup/static_evidence.py` | red / owned | S-00-owned runtime checkpoint boundary for static extraction plus normalized enrichment before admission handoff. |
| Legacy static surface wrapper | `api/pipeline/s00_setup/static_surface_extraction.py` | red / owned | Compatibility wrapper that preserves the older static surface seam name. |
| Static analysis implementation | `api/pipeline/s00_setup/static_analysis.py` | red / owned | Current implementation that extracts strings, IAT hints, static sentinels, call graph, and data type surfaces when available. |
| Static enrichment normalizer | `api/pipeline/s00_setup/static_enrichment.py` | red / owned | Normalizes callable inventory, prerequisite hints, deferred snippets, and ambiguity into additive `static_enrichment.json`. |
| Admission/handoff boundary | `api/pipeline/s00_setup/admission_handoff.py` | red / owned | S-00-owned runtime checkpoint boundary that turns setup/static evidence into the admitted S-01 handoff packet without changing packet shape. |
| Legacy packet producer wrapper | `api/pipeline/s00_setup/s01_handoff_packet.py` | red / owned | Compatibility wrapper that preserves existing imports while routing through the admission/handoff boundary. |
| Handoff packet builder | `api/pipeline/core/s00_s01_handoff.py` | yellow / dependency | Shared seam helper that normalizes S-00 output into the S-01 handoff packet. |
| S-01 consumer | `api/pipeline/s01_unlock/__init__.py` | yellow / downstream dependency | Reads the admitted S-00 slice when available and falls back to legacy context when needed. |

## Artifact Trace

| Artifact | Marker | Expected runtime home | Why it matters |
| --- | --- | --- | --- |
| `status.json` | gray / upstream | `local-data/artifacts/<job_id>/status.json` | Job and pipeline state; not an S-00-owned artifact. |
| `upload_investigation.json` | gray / upstream | `local-data/artifacts/<job_id>/upload_investigation.json` | Intake/discovery trace for how the DLL entered the system. |
| `invocables_map.json` | gray / upstream | `local-data/artifacts/<job_id>/invocables_map.json` | Canonical callable skeleton consumed by S-00 and later stages. |
| `discovery_meta.json` | gray / upstream | `local-data/artifacts/<job_id>/discovery_meta.json` | Discovery cache, bridge, and schema-quality metadata. |
| `sentinel_calibration.json` | green / output | `local-data/artifacts/<job_id>/sentinel_calibration.json` | S-00 sentinel/error-code baseline for unlock and probe work. |
| `vocab.json` | green / output | `local-data/artifacts/<job_id>/vocab.json` | Shared setup vocabulary used by downstream stages. |
| `static_analysis.json` | green / output | `local-data/artifacts/<job_id>/static_analysis.json` | Static evidence packet: strings, imports, PE hints, and harvested static surfaces. |
| `static_enrichment.json` | green / output | `local-data/artifacts/<job_id>/static_enrichment.json` | Normalized S-00 static guidance: callable inventory, prerequisite hints, deferred snippets, and ambiguity. |
| `call_graph.json` | green / optional output | `local-data/artifacts/<job_id>/call_graph.json` | Optional cheap structural prior when call graph evidence exists. |
| `ghidra_data_types.json` | green / optional output | `local-data/artifacts/<job_id>/ghidra_data_types.json` | Optional struct, enum, typedef, and data type hints. |
| `s01_handoff_packet.json` | green / output | `local-data/artifacts/<job_id>/s01_handoff_packet.json` | Organized S-00 to S-01 packet with admitted, deferred, ambiguous, and target surfaces. |

## Expected Homes

| Thing | Expected home |
| --- | --- |
| Live S-00 implementation | `api/pipeline/s00_setup/` |
| S-00 live artifact contract | `api/pipeline/s00_setup/ARTIFACTS.md` |
| S-00 live guarantees and caveats | `api/pipeline/s00_setup/LIVE-CONTRACT.md` |
| S-00 dependency map | `api/pipeline/s00_setup/SYSTEMS.md` |
| S-00 trace and surface ownership | `api/pipeline/s00_setup/TRACE.md` |
| Shared runner | `api/pipeline/runner.py` |
| Shared pipeline helpers | `api/pipeline/core/` |
| Pre-stage discovery | `api/services/discovery.py` |
| API intake | `api/routes/main.py` |
| Runtime job artifacts | `local-data/artifacts/<job_id>/` |
| Stage split doctrine and target design | `docs/architecture/stage_split/` |

## Organization Rule

S-00 should not grow local copies of route, worker, discovery, or runner code
unless ownership actually changes. The stage folder should instead expose:

- owned implementation files as `red / owned`
- required shared dependencies as `yellow / dependency`
- pre-stage feeders as `gray / upstream`
- emitted artifacts as `green / output`

This gives the stage a single operator-readable home without making the code
tree lie about ownership.
