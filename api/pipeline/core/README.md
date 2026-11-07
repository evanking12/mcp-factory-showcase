# Pipeline Core Shared Surfaces

`api/pipeline/core/` is shared pipeline infrastructure. It is not a numbered
stage and it is not automatically owned by S-00, S-01, or any other stage.

Use stage-local `TRACE.md` files to explain which core files matter to a stage.
If a core file is stage-critical, mark it as `yellow / dependency` unless the
file has actually been migrated into the stage folder.

## How To Read This Folder

Start with the owning stage `TRACE.md` when asking why a stage cares about a
core file. Start here when asking what kind of shared system the file belongs
to.

## Shared System Groups

| System group | Example files | Meaning |
| --- | --- | --- |
| Stage seams and contracts | `s00_s01_handoff.py`, `handoff_contract.py`, `system_contract.py` | Shared packet, transition, and contract utilities used by one or more stages. |
| Runtime and checkpoint mechanics | `checkpoint.py`, `cluster_checkpoint.py`, `compatibility.py`, `runtime_api.py`, `types.py` | Shared execution mechanics that stages rely on but do not individually own. |
| Evidence and reusable truth | `evidence_graph.py`, `evidence_candidates.py`, `reusable_truth.py`, `finding_status.py` | Shared evidence structures, status taxonomy, and reusable truth surfaces. |
| Provenance and static-prior support | `ghidra_provenance.py`, `dependency_class_inference.py`, `init_group_inference.py`, `vocab.py` | Shared helpers for provenance, dependency hints, init grouping, and vocabulary. |
| Coordination and planning | `macro_coordinator.py`, `slice_execution_coordinator.py`, `shard_merge_coordinator.py`, `package_frontier_planner.py` | Shared coordination systems, not stage-local truth by themselves. |
| Decomposition and package frontier | `decomposition_contract.py`, `package_intake_shard_runner.py`, `shard_inventory_emitter.py`, `package_floor_validity.py` | Shared package/decomposition systems used by frontier and floor workflows. |
| Campaign, proving, and regression support | `campaign_stages.py`, `run_authority.py`, `design_suite_*`, `spectrum_*` | Governance, proving, campaign, or regression support surfaces. |

## Non-Goals

- This folder is not the live stage map.
- This folder is not the place to describe what S-00 through S-07 guarantee
  today.
- This folder should not hide stage behavior that belongs in a numbered stage
  sticky doc.

## Ownership Rule

If a stage depends on a core file, the owning stage doc should say why.

The expected home is:

| Question | Expected home |
| --- | --- |
| What does the shared helper do generally? | This README or a core-level doc. |
| Why does S-00 need it? | `api/pipeline/s00_setup/TRACE.md` or `SYSTEMS.md`. |
| What artifact contract does it affect? | The stage's `ARTIFACTS.md` and `LIVE-CONTRACT.md`. |
| Is it live behavior or target design? | Stage sticky docs for live behavior; `docs/architecture/` for target design. |

Do not infer stage ownership from file proximity. `core` means shared dependency
until a stage-local trace says otherwise.
