# S-05 Trace / Surface Map

This is the operator map for S-05. It explains the files and artifacts that
matter for enrichment and verification without making S-05 own synthesis or
final gap resolution.

## Legend

| Marker | Meaning |
| --- | --- |
| `red / owned` | S-05 canonical implementation or S-05-owned live contract. |
| `yellow / dependency` | Required by S-05 but owned by a shared layer or adjacent stage. |
| `gray / upstream` | Runs before S-05 and feeds or invokes it. |
| `green / output` | Artifact, packet, or context surface emitted for later consumers. |

## Runtime Trace

| Step | Surface | Marker | Why S-05 cares |
| --- | --- | --- | --- |
| Pipeline runner invokes S-05 | `api/pipeline/runner.py` | yellow / dependency | Controls when enrichment runs after synthesis. |
| Synthesis output | `api/pipeline/s04_synthesis/` | gray / upstream | Supplies API reference and synthesis context. |
| S-05 entrypoint | `api/pipeline/s05_enrichment/__init__.py` | red / owned | Owns the live enrichment stage boundary. |
| S-05 status helpers | `api/pipeline/s05_enrichment/status.py` | red / owned | Emits parent-compatible S-05A/B/C runtime status. |
| S-05A wrapper | `api/pipeline/s05_enrichment/schema_backfill.py` | red / owned | Owns the schema-backfill runtime boundary. |
| S-05B wrapper | `api/pipeline/s05_enrichment/verification_replay.py` | red / owned | Owns the verification-replay runtime boundary. |
| S-05C wrapper | `api/pipeline/s05_enrichment/read_to_write_chaining.py` | red / owned | Owns the read-to-write chaining runtime boundary. |
| Backfill logic | `api/pipeline/s05_enrichment/backfill.py` | red / owned | Backfills schema details and parameter descriptions. |
| Verification logic | `api/pipeline/s05_enrichment/verify.py` | red / owned | Verifies working calls and state-changing claims. |
| Read-chain analysis | `api/pipeline/s05_enrichment/mc5_chain_reads.py` | red / owned | Records read-to-write chaining decisions when available. |
| S-06 consumer | `api/pipeline/s06_gaps/__init__.py` | yellow / downstream dependency | Reads unresolved cases and verification results for final retries. |

## Artifact Trace

| Artifact | Marker | Expected runtime home | Why it matters |
| --- | --- | --- | --- |
| `backfill_result.json` | green / optional output | `local-data/artifacts/<job_id>/backfill_result.json` | Records schema backfill statistics. |
| `verification-report.json` | green / optional output | `local-data/artifacts/<job_id>/verification-report.json` | Distinguishes verified, inferred, and failed outcomes. |
| `mc-decisions/mc5-post-verification.json` | green / optional output | `local-data/artifacts/<job_id>/mc-decisions/mc5-post-verification.json` | Records read-to-write chaining decisions. |
| `mcp_schema_post_discovery.json` | green / optional output | `local-data/artifacts/<job_id>/mcp_schema_post_discovery.json` | Captures schema after enrichment/backfill. |
| `evidence/stage-05a-schema-backfill/*` | green / additive alias | session snapshot / capture aliases | Stage-owned aliases for S-05A outputs. |
| `evidence/stage-05b-verification-replay/*` | green / additive alias | session snapshot / capture aliases | Stage-owned aliases for S-05B outputs. |
| `evidence/stage-05c-read-to-write-chaining/*` | green / additive alias | session snapshot / capture aliases | Stage-owned aliases for S-05C outputs. |

## Expected Homes

| Thing | Expected home |
| --- | --- |
| Live S-05 implementation | `api/pipeline/s05_enrichment/` |
| S-05 artifact contract | `api/pipeline/s05_enrichment/ARTIFACTS.md` |
| S-05 guarantees and caveats | `api/pipeline/s05_enrichment/LIVE-CONTRACT.md` |
| S-05 dependency map | `api/pipeline/s05_enrichment/SYSTEMS.md` |
| S-05 trace and surface ownership | `api/pipeline/s05_enrichment/TRACE.md` |
| Runtime job artifacts | `local-data/artifacts/<job_id>/` |
