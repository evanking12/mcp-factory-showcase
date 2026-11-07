# S-04 Trace / Surface Map

This is the operator map for S-04. It explains the files and artifacts that
matter for synthesis without making S-04 own probing, reconciliation, or final
closure.

## Legend

| Marker | Meaning |
| --- | --- |
| `red / owned` | S-04 canonical implementation or S-04-owned live contract. |
| `yellow / dependency` | Required by S-04 but owned by a shared layer or adjacent stage. |
| `gray / upstream` | Runs before S-04 and feeds or invokes it. |
| `green / output` | Artifact, packet, or context surface emitted for later consumers. |

## Runtime Trace

| Step | Surface | Marker | Why S-04 cares |
| --- | --- | --- | --- |
| Pipeline runner invokes S-04 | `api/pipeline/runner.py` | yellow / dependency | Controls when synthesis runs after reconciliation. |
| Reconciled findings | `api/pipeline/s03_reconcile/` | gray / upstream | Supplies corrected behavior evidence. |
| S-04 entrypoint | `api/pipeline/s04_synthesis/__init__.py` | red / owned | Owns the live synthesis stage boundary. |
| Synthesis logic | `api/pipeline/s04_synthesis/synthesize.py` | red / owned | Builds API reference content from accumulated evidence. |
| Init clue analysis | `api/pipeline/s04_synthesis/mc4_init_clues.py` | red / owned | Records synthesis-derived init clues when available. |
| S-05 consumer | `api/pipeline/s05_enrichment/__init__.py` | yellow / downstream dependency | Uses synthesis output for schema enrichment and verification context. |

## Artifact Trace

| Artifact | Marker | Expected runtime home | Why it matters |
| --- | --- | --- | --- |
| `api_reference.md` | green / output | `local-data/artifacts/<job_id>/api_reference.md` | Human-readable API reference built from evidence. |
| `mc-decisions/mc4-post-synthesis.json` | green / optional output | `local-data/artifacts/<job_id>/mc-decisions/mc4-post-synthesis.json` | Records init clues inferred during synthesis. |
| `evidence/stage-04-synthesis/synthesis-input-snapshot.json` | green / optional output | `local-data/artifacts/<job_id>/evidence/stage-04-synthesis/synthesis-input-snapshot.json` | Captures synthesis inputs for auditability. |
| `evidence/stage-04-synthesis/synthesis-coverage-check.json` | green / optional output | `local-data/artifacts/<job_id>/evidence/stage-04-synthesis/synthesis-coverage-check.json` | Records synthesis coverage. |

## Expected Homes

| Thing | Expected home |
| --- | --- |
| Live S-04 implementation | `api/pipeline/s04_synthesis/` |
| S-04 artifact contract | `api/pipeline/s04_synthesis/ARTIFACTS.md` |
| S-04 guarantees and caveats | `api/pipeline/s04_synthesis/LIVE-CONTRACT.md` |
| S-04 dependency map | `api/pipeline/s04_synthesis/SYSTEMS.md` |
| S-04 trace and surface ownership | `api/pipeline/s04_synthesis/TRACE.md` |
| Runtime job artifacts | `local-data/artifacts/<job_id>/` |
