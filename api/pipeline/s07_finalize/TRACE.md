# S-07 Trace / Surface Map

This is the operator map for S-07. It explains the files and artifacts that
matter for finalization without making S-07 own the upstream evidence work.

## Legend

| Marker | Meaning |
| --- | --- |
| `red / owned` | S-07 canonical implementation or S-07-owned live contract. |
| `yellow / dependency` | Required by S-07 but owned by a shared layer or adjacent stage. |
| `gray / upstream` | Runs before S-07 and feeds or invokes it. |
| `green / output` | Artifact, packet, or context surface emitted for later consumers. |

## Runtime Trace

| Step | Surface | Marker | Why S-07 cares |
| --- | --- | --- | --- |
| Pipeline runner invokes S-07 | `api/pipeline/runner.py` | yellow / dependency | Controls when finalization runs after gap resolution. |
| Upstream evidence stack | `api/pipeline/s00_setup/` through `api/pipeline/s06_gaps/` | gray / upstream | Supplies final vocab, findings, synthesis, verification, and open gaps. |
| S-07 entrypoint | `api/pipeline/s07_finalize/__init__.py` | red / owned | Owns the live finalization stage boundary. |
| Behavioral spec output | `api/pipeline/s07_finalize/behavioral_spec.py` | red / owned | Builds typed behavioral summary when available. |
| Harmonization and finalize close path | `api/pipeline/s07_finalize/harmonize.py` | red / owned | Performs deterministic final finding repairs, bounded optional description synthesis, final vocab/schema-evolution writes, and S-07 span status. |
| Operator/UI consumer | API/session surfaces | yellow / downstream dependency | Presents final closure, open questions, and artifacts to the operator. |

## Artifact Trace

| Artifact | Marker | Expected runtime home | Why it matters |
| --- | --- | --- | --- |
| `behavioral_spec.py` | green / optional output | `local-data/artifacts/<job_id>/behavioral_spec.py` | Typed behavioral summary of the API surface. |
| `harmonization_report.json` | green / optional output | `local-data/artifacts/<job_id>/harmonization_report.json` | Records final deterministic repairs. |
| `vocab.json` | green / output | `local-data/artifacts/<job_id>/vocab.json` | Captures final vocabulary and DLL description when updated. |
| Contract artifacts | green / optional output | `local-data/artifacts/<job_id>/` | Session, stage, transition, and cohesion surfaces for review. |

## Expected Homes

| Thing | Expected home |
| --- | --- |
| Live S-07 implementation | `api/pipeline/s07_finalize/` |
| S-07 artifact contract | `api/pipeline/s07_finalize/ARTIFACTS.md` |
| S-07 guarantees and caveats | `api/pipeline/s07_finalize/LIVE-CONTRACT.md` |
| S-07 dependency map | `api/pipeline/s07_finalize/SYSTEMS.md` |
| S-07 trace and surface ownership | `api/pipeline/s07_finalize/TRACE.md` |
| Runtime job artifacts | `local-data/artifacts/<job_id>/` |
