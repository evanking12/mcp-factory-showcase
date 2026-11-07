# Live Pipeline Stage Map

Live stage truth lives in `api/pipeline/<stage>/`. Architecture and migration
doctrine live under `docs/architecture/stage_split/`, but stage guarantees,
owned artifacts, and current consumers belong beside the stage code.

## Current Stages

| Stage | Folder | Dominant job |
| --- | --- | --- |
| S-00 parent | `s00_setup` | Legacy compatibility parent for the split S-00 runtime checkpoints. |
| S-00A | `s00_setup` | `s00_setup_baseline`: build sentinel/vocab setup baseline. |
| S-00B | `s00_setup` | `s00_static_evidence`: build static analysis and enrichment context. |
| S-00C | `s00_setup` | `s00_admission_handoff`: build the S-00 to S-01 handoff packet. |
| S-01 | `s01_unlock` | Discover or defer write-mode unlock conditions. |
| S-02 parent | `s02_probe` | Legacy compatibility parent for the split S-02 runtime checkpoints. |
| S-02A | `s02_probe` | `s02_probe_ordering`: order probe work and preserve prerequisite planning. |
| S-02B | `s02_probe` | `s02_invocation_execution`: construct arguments, execute calls, and collect raw observations. |
| S-02C | `s02_probe` | `s02_evidence_capture`: persist evidence, findings, checkpoint state, and boundary recalibration. |
| S-03 | `s03_reconcile` | Reconcile findings against probe evidence and classify write failures. |
| S-04 | `s04_synthesis` | Synthesize accumulated evidence into API documentation. |
| S-05 | `s05_enrichment` | Backfill schema details and verify successful calls. |
| S-06 | `s06_gaps` | Retry unresolved functions and generate remaining clarification gaps. |
| S-07 | `s07_finalize` | Harmonize final truth and emit closure artifacts. |

## Shared Surfaces Around Stages

Not every file touched by a stage belongs in that stage folder. The live code
path is layered:

| Surface | Role | Stage ownership rule |
| --- | --- | --- |
| `api/routes/` | API intake and operator-facing request routes. | Gray/upstream unless a stage route is explicitly owned. |
| `api/infra/` | Worker and runtime job infrastructure. | Gray/upstream or yellow/dependency. |
| `api/services/` | Discovery and shared service systems. | Gray/upstream for stage inputs. |
| `api/pipeline/runner.py` | Stage orchestration and execution order. | Yellow/dependency for numbered stages. |
| `api/pipeline/core/` | Shared pipeline utilities and seam helpers. | Yellow/dependency unless a file is explicitly migrated into a stage. |
| `api/pipeline/sNN_*` | Numbered stage implementation and live stage truth. | Red/owned for that stage. |

Stage folders should not duplicate route, worker, discovery, or runner code just
to appear self-contained. They should disclose those dependencies in their
sticky docs and trace maps.

## S-00 Runtime Split

S-00 is now split at runtime into three checkpoint IDs while preserving the
legacy `s00_setup` identity as a compatibility parent:

- `s00_setup_baseline`
- `s00_static_evidence`
- `s00_admission_handoff`

All three live in `api/pipeline/s00_setup/` because the code ownership is still
one S-00 package. The split is for runtime observability, checkpoint/resume
boundaries, and failure attribution. It is not permission to remove legacy
`s00_setup` paths or wrappers.

## S-02 Runtime Split

S-02 is now split at runtime into three checkpoint IDs while preserving the
legacy `s02_probe` identity as the compatibility parent:

- `s02_probe_ordering`
- `s02_invocation_execution`
- `s02_evidence_capture`

All three live in `api/pipeline/s02_probe/`. The split is for runtime
observability, checkpoint/resume boundaries, artifact ownership, and failure
attribution. The legacy `s02_probe` parent still means the full probe stage has
completed and must not be removed without a separate compatibility campaign.

## Surface Map Legend

Use this legend in stage trace docs:

| Marker | Meaning |
| --- | --- |
| `red / owned` | Canonical stage implementation or stage-owned live contract. |
| `yellow / dependency` | Required by the stage but owned by a shared layer. |
| `gray / upstream` | Happens before the stage and feeds or invokes it. |
| `green / output` | Artifact, packet, or context surface emitted for later consumers. |

## Sticky Docs

Every numbered stage folder must maintain:

- `README.md`: human entrypoint and runtime owner files.
- `PURPOSE.md`: dominant assignment and non-goals.
- `FLOW.md`: live execution flow.
- `ARTIFACTS.md`: owned inputs, outputs, aliases, and consumers.
- `SYSTEMS.md`: depended-on systems the stage does not own.
- `LIVE-CONTRACT.md`: current guarantees, caveats, and handoff status.
- `TRACE.md`: red/yellow/gray/green surface map for stage ownership.
- `FAMILY-BLOCKERS.md`: blocker families the stage handles, defers, does not
  own, or exposes as architecture gaps.

## Migration Test Selection

Use the surface map marker to choose the minimum test blast radius:

| Marker | Migration meaning | Minimum test implication |
| --- | --- | --- |
| `red / owned` | Stage-owned implementation changed. | Run the stage-local tests plus its artifact and contract tests. |
| `yellow / dependency` | Shared dependency changed. | Run tests for every stage that lists the dependency in `TRACE.md`. |
| `gray / upstream` | Intake, discovery, worker, or other feeder changed. | Run upstream tests plus the first affected stage seam. |
| `green / output` | Emitted artifact shape or path changed. | Run producer, packaging, and downstream consumer tests. |

These are minimum local gates. Broad non-regression claims still require the
applicable tier from `docs/architecture/testing_strategy/REGRESSION-LADDER.md`.

## Trace-Oriented Walkthroughs

For stage-chain questions, prefer the trace format:

| Question | Meaning |
| --- | --- |
| What runs? | The runtime step or stage behavior. |
| Where is it implemented? | The owning file or module. |
| What does it produce? | The artifact or context mutation. |
| Why does it matter? | The decision or downstream utility it enables. |
| Who consumes it next? | The next stage, route, snapshot, UI, or test surface. |

## Live Truth Rule

If stage code changes but the stage sticky docs do not, the implementation is
not reviewable. If architecture doctrine changes but live behavior does not,
record it in `docs/architecture/stage_split` and do not describe it as live
truth until the stage folder mirrors it.
