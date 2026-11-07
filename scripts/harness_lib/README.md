# Harness Capture And Session Collection

This folder is the save-session implementation surface for local capture and
post-run collection. It is already split in a useful way; the main gap was
explicit ownership, not code placement.

## Ownership Map

### `capture.py`

Purpose:
- local capture entrypoint
- snapshot download/materialization
- session folder creation
- capture manifest and provenance writing

Use when:
- a run has finished and a local session needs to be saved
- checkpoint-aware snapshot materialization is needed
- emitted vs recovered vs synthesized provenance must be preserved

Primary outputs:
- local session tree
- `snapshot-manifest.json`
- `snapshot-profile.json`
- checkpoint copies and capture notes

### `collector.py`

Purpose:
- contract validation
- session analysis and derived output generation
- ledger row construction
- stage/transition/cohesion readback

Use when:
- a captured session needs to become a comparable measurement artifact
- dashboard row / run validity / artifact index / validation report are needed
- campaign or run truth must be correlated into ledger form

Primary outputs:
- `human/summary.md`
- `human/dashboard-row.json`
- `human/session-save-meta.json`
- run-validity, KPI, audit, artifact-index, and ledger payloads

### `validation_report.py`

Purpose:
- focused validation-report generation shared by collection flows

Use when:
- collector needs a reusable validation summary rather than ad hoc formatting

## Related Files Outside This Folder

### `api/routes/routes_session.py`

Purpose:
- remote API snapshot assembly
- ZIP packaging of run artifacts from blob-backed job state

Why it is separate:
- this is API/server-side snapshot construction, not local capture logic

### `api/analysis/cohesion.py`

Purpose:
- contract/cohesion artifact emission used by snapshots and collection

### `api/pipeline/core/checkpoint.py`

Purpose:
- checkpoint persistence and restore boundaries used by capture and iteration

## Navigation Rule

If the question is:

- "How do we fetch/materialize a session?"
  - start in `capture.py`
- "How do we validate and summarize a saved session?"
  - start in `collector.py`
- "How does the API produce the snapshot ZIP?"
  - start in `api/routes/routes_session.py`
- "How do checkpoints shape what can be resumed or archived?"
  - start in `api/pipeline/core/checkpoint.py`

## Architectural Rule

Keep one user-facing save-session flow, but do not collapse all behavior into
one giant script.

Preferred shape:
- one entrypoint
- one canonical manifest/provenance model
- multiple owned components with clear boundaries

That keeps the system easier to reason about for both humans and agents.
