# S-06 Trace / Surface Map

This is the operator map for S-06. It explains the files and artifacts that
matter for gap resolution without making S-06 own earlier proof or final
closure.

## Legend

| Marker | Meaning |
| --- | --- |
| `red / owned` | S-06 canonical implementation or S-06-owned live contract. |
| `yellow / dependency` | Required by S-06 but owned by a shared layer or adjacent stage. |
| `gray / upstream` | Runs before S-06 and feeds or invokes it. |
| `green / output` | Artifact, packet, or context surface emitted for later consumers. |

## Runtime Trace

| Step | Surface | Marker | Why S-06 cares |
| --- | --- | --- | --- |
| Pipeline runner invokes S-06 | `api/pipeline/runner.py` | yellow / dependency | Controls when gap resolution runs after enrichment. |
| Verification and synthesis context | `api/pipeline/s04_synthesis/`, `api/pipeline/s05_enrichment/` | gray / upstream | Supplies unresolved functions, enriched schema, and verification results. |
| S-06 entrypoint | `api/pipeline/s06_gaps/__init__.py` | red / owned | Owns the live gap-resolution stage boundary. |
| Gap resolution | `api/pipeline/s06_gaps/gap_resolution.py` | red / owned | Retries unresolved functions and prepares clarification questions. |
| Final unlock analysis | `api/pipeline/s06_gaps/mc6_final_unlock.py` | red / owned | Handles late-stage unlock/gap reasoning when available. |
| S-07 consumer | `api/pipeline/s07_finalize/__init__.py` | yellow / downstream dependency | Reads gap outcomes and remaining questions for closure. |

## Artifact Trace

| Artifact | Marker | Expected runtime home | Why it matters |
| --- | --- | --- | --- |
| `mc-decisions/mc6-post-gap-resolution.json` | green / optional output | `local-data/artifacts/<job_id>/mc-decisions/mc6-post-gap-resolution.json` | Records final unlock/gap decisions. |
| `mcp_schema_post_gap_resolution.json` | green / optional output | `local-data/artifacts/<job_id>/mcp_schema_post_gap_resolution.json` | Captures schema after gap-resolution attempts. |
| `mcp_schema_post_clarification.json` | green / optional output | `local-data/artifacts/<job_id>/mcp_schema_post_clarification.json` | Captures schema after clarification question generation. |
| `explore_questions` | green / optional output | `local-data/artifacts/<job_id>/status.json` | Surfaces remaining user clarification questions. |

## Expected Homes

| Thing | Expected home |
| --- | --- |
| Live S-06 implementation | `api/pipeline/s06_gaps/` |
| S-06 artifact contract | `api/pipeline/s06_gaps/ARTIFACTS.md` |
| S-06 guarantees and caveats | `api/pipeline/s06_gaps/LIVE-CONTRACT.md` |
| S-06 dependency map | `api/pipeline/s06_gaps/SYSTEMS.md` |
| S-06 trace and surface ownership | `api/pipeline/s06_gaps/TRACE.md` |
| Runtime job artifacts | `local-data/artifacts/<job_id>/` |
