# S-03 Trace / Surface Map

This is the operator map for S-03. It explains the files and artifacts that
matter for reconciliation without making S-03 own probing or synthesis.

## Legend

| Marker | Meaning |
| --- | --- |
| `red / owned` | S-03 canonical implementation or S-03-owned live contract. |
| `yellow / dependency` | Required by S-03 but owned by a shared layer or adjacent stage. |
| `gray / upstream` | Runs before S-03 and feeds or invokes it. |
| `green / output` | Artifact, packet, or context surface emitted for later consumers. |

## Runtime Trace

| Step | Surface | Marker | Why S-03 cares |
| --- | --- | --- | --- |
| Pipeline runner invokes S-03 | `api/pipeline/runner.py` | yellow / dependency | Controls when reconciliation runs after probing. |
| Probe evidence | `api/pipeline/s02_probe/` | gray / upstream | Supplies raw observations and findings to reconcile. S-03 prefers the S-02C durable probe-log alias and falls back to legacy probe logs. |
| S-03 entrypoint | `api/pipeline/s03_reconcile/__init__.py` | red / owned | Owns the live reconcile stage boundary. |
| Reconcile logic | `api/pipeline/s03_reconcile/reconcile.py` | red / owned | Repairs or classifies findings against observed evidence. |
| Write-failure analysis | `api/pipeline/s03_reconcile/mc3_write_analysis.py` | red / owned | Separates global unlock problems from per-function failures. |
| Sentinel catalog | `api/pipeline/s03_reconcile/sentinel_catalog.py` | red / owned | Promotes observed sentinel evidence when available. |
| S-04 consumer | `api/pipeline/s04_synthesis/__init__.py` | yellow / downstream dependency | Reads reconciled findings for documentation synthesis. |

## Artifact Trace

| Artifact | Marker | Expected runtime home | Why it matters |
| --- | --- | --- | --- |
| `mc-decisions/mc3-post-reconcile.json` | green / optional output | `local-data/artifacts/<job_id>/mc-decisions/mc3-post-reconcile.json` | Records MC-3 write-failure decisions. |
| `sentinel_catalog.json` | green / optional output | `local-data/artifacts/<job_id>/sentinel_catalog.json` | Promotes observed sentinel evidence for later interpretation. |
| `evidence/stage-02c-evidence-capture/probe-log.json` | gray / upstream input | `local-data/artifacts/<job_id>/evidence/stage-02c-evidence-capture/probe-log.json` | Preferred durable S-02C-owned probe evidence consumed before legacy `explore_probe_log.json`. |

## Expected Homes

| Thing | Expected home |
| --- | --- |
| Live S-03 implementation | `api/pipeline/s03_reconcile/` |
| S-03 artifact contract | `api/pipeline/s03_reconcile/ARTIFACTS.md` |
| S-03 guarantees and caveats | `api/pipeline/s03_reconcile/LIVE-CONTRACT.md` |
| S-03 dependency map | `api/pipeline/s03_reconcile/SYSTEMS.md` |
| S-03 trace and surface ownership | `api/pipeline/s03_reconcile/TRACE.md` |
| Runtime job artifacts | `local-data/artifacts/<job_id>/` |
