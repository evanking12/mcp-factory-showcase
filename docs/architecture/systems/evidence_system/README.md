# Evidence System

## Purpose

The evidence system owns durable truth surfaces and reusable run history.

Its job is to make evidence reviewable, attributable, and comparable across
time.

Without it, the product cannot distinguish:

- real improvement
- hidden-variable contamination
- stale claims
- incomparable runs

## Owned Surfaces

Primary owned areas and artifacts:

- `sessions/`
- `artifacts/`
- `local-data/`
- collector and ledger surfaces:
  - `scripts/harness_lib/collector.py`
  - `sessions/ledger/run_ledger.jsonl`
- roadblock records under `bugs/`
- compare artifacts and campaign attribution outputs

Related code ownership often spans:

- `api/infra/storage.py`
- `api/infra/storage_api.py`
- checkpoint persistence surfaces

## Primary Inputs

- job results
- pipeline checkpoints
- stage snapshots
- collected artifacts from routes, workers, and pipeline stages
- compare-run metadata
- campaign identifiers and profile keys

## Primary Outputs

- session manifests
- checkpoint snapshots
- run ledger rows
- compare reports
- campaign attribution artifacts
- roadblock records
- evidence stacks used by the dashboard and analysis flows

## Public Contracts

Critical contracts include:

- strict artifact schema expectations
- collector output shape
- checkpoint persistence rules
- run ledger row completeness
- comparable profile key semantics
- attribution and campaign cohesion surfaces

## Invariants

- campaign-backed claims require attribution coherence
- comparable runs must match profile keys, not just names
- artifacts should be written under session or artifact roots, not repo root
- durable evidence should preserve provenance, not just convenient summaries
- if behavior improves without emitting reusable evidence, specialization is
  incomplete

## Common Failure Modes

- missing ledger fields poisoning comparison
- stale or partial artifacts being read as complete truth
- compare-run claims made across incomparable profiles
- same-DLL and cross-DLL attribution blurred together
- session snapshots missing the true stage boundary where failure happened

## Observability Gaps

Current recurring gaps include:

- coverage summaries are still easier to derive from artifacts than to read
  directly in the product
- roadblock artifacts exist but are not yet surfaced well enough to operators
- suite-progress and capability-progress summaries still need stronger evidence
  rollups

## Typical Tests And Checks

When this system changes, likely checks include:

- collector tests
- checkpoint tests
- compare-run tests
- campaign attribution tests
- `python scripts/verify_sync.py --tier A`

## Agent Guidance

Use this doc before editing when the task involves:

- session artifact structure
- ledger correctness
- compare-run interpretation
- campaign attribution
- checkpoint completeness
- reusable evidence or provenance drift

Default related skills:

- `ledger-auditor`
- `cross-dll-evidence-auditor`
- `roadblock-handler`

## Do Not Own

The evidence system does not own:

- live bridge or worker behavior
- probe-loop strategy
- dashboard layout
- governance law
