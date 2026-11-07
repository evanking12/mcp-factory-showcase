# Chart Conventions

Use these rules so the chart set stays stable and learnable as the repo evolves.

## Audience And Scope

- `01-engineering-overview-4/`
  - Canonical source set for understanding what the code does.
- `02-architecture-thesis-5/`
  - Reuses the engineering view, then adds the compounding/truth claim.
- `03-full-thesis-6-cross-dll/`
  - Reuses the earlier views, then adds campaign and cross-DLL learning.

Default rule:

- refine the 4-chart engineering set first
- only then propagate changes upward into the 5- and 6-chart sets

## Layout Rules

- Use top-down flow for system/dataflow and truth/compounding charts.
- Use left-to-right flow for stage progression charts.
- Keep node labels short and literal.
- Prefer one meaning per node.
- Avoid mixing implementation detail and thesis framing in the same chart.

## Naming Rules

Canonical stage model:

- `S-00 setup`
- `S-01 write-unlock`
- `S-02 probe-loop`
- `S-03 reconcile`
- `S-04 synthesis`
- `S-05 enrichment`
- `S-06 gap-resolution`
- `S-04R synthesis-refresh`
- `S-07 finalize`

Important naming note:

- charts should follow the canonical stage model from `api/pipeline/core/handoff_contract.py`
- session snapshots may still include older historical folder names from `api/routes/routes_session.py`
- those legacy names are capture-layout aliases only
- the snapshot now exposes:
  - `stage-index.json`
  - `canonical-stage-model.json`
  - `capture-layout-stage-aliases.json`
- treat those files, plus `evidence/`, as the source of truth for stage semantics

## Legend

- `ExploreRuntime`
  - Immutable run-shape decisions.
- `ExploreContext`
  - Mutable learned state carried through the run.
- `Checkpoint`
  - Resume and archival boundary for trusted state.
- `Session capture`
  - Reviewable artifact bundle assembled from run outputs.
- `Collector`
  - Audit and reporting surface that turns raw artifacts into validity and ledger outputs.
- `Package campaign`
  - Curated software-package intake with per-DLL measurement and package-level decisions.
- `Lane gate`
  - Pre-explore trust check that can block noisy campaign execution.
- `Blocker harvest`
  - Per-DLL and campaign-level blocker-family classification used for system selection.
- `Overlap baseline`
  - Expansion-wave comparison surface that carries forward only the previously trusted DLL overlap.

## Learning Order

Read and explain these in order:

1. system overview and dataflow
2. stage model
3. context and memory model
4. status and classification
5. truth, replay, checkpoints, and compounding
6. campaign and cross-DLL evidence flow
7. package-level blocker harvesting and lane trust
8. overlap-baseline comparison for package expansion

## Ownership Test

You understand the architecture at a useful level when you can explain:

1. what each stage is supposed to add
2. where learned state lives during a run
3. what gets persisted for later runs
4. what makes a result trustworthy versus merely interesting
5. how replay-backed gains differ from cold-run robustness
6. where cross-DLL learning enters the system
7. how package-level blocker harvesting differs from batch execution
8. why clean trust alone does not make an expansion wave promotion-safe
