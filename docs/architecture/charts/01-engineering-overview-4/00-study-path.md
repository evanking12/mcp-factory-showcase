# Study Path

This file exists to help you learn the architecture, not just view diagrams.

If you want the full reading sequence with code anchors, start with:

- `ARCHITECTURE-WALK.md`

## Phase 1: Orient Yourself

Read:

1. `01-system-overview-dataflow.md`
2. `02-stage-model.md`

Then answer:

1. Where does a run start?
2. What are the major outputs of a run?
3. Which parts are pipeline execution versus audit/capture?

## Phase 2: Understand Memory

Read:

1. `04-context-memory-model.md`
2. `api/pipeline/core/types.py`
3. `api/pipeline/core/checkpoint.py`
4. `api/pipeline/core/cluster_checkpoint.py`

Then answer:

1. What is immutable during a run?
2. What changes as the run learns?
3. What can survive into the next run?
4. What can survive below the stage level as a semantically coherent rerun unit?

## Phase 3: Understand Claims

Read:

1. `03-status-classification.md`
2. `api/pipeline/core/finding_status.py`
3. `scripts/harness_lib/collector.py`

Then answer:

1. How does a raw probe outcome become a canonical status?
2. What makes one result stronger than another?
3. Where does the repo enforce comparability and validity?

## Phase 4: Own The Model

Once the 4-chart set feels comfortable, move to:

1. `../02-architecture-thesis-5/05-truth-replay-checkpoints-compounding.md`
2. `../03-full-thesis-6-cross-dll/06-campaign-cross-dll-evidence-flow.md`

Then answer:

1. Why is replay useful but not identical to cold robustness?
2. What prevents compounding from becoming fake progress?
3. How would cross-DLL learning actually change a later run?

## Minimal Mastery Standard

You are ready to direct work at the right level when you can explain:

- the stage model without looking
- the difference between `ExploreRuntime` and `ExploreContext`
- where checkpoints sit in the loop
- where session capture and collector logic sit in the loop
- why audited truth matters as much as raw unlock count
