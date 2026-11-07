# Architecture Walk

This is the default learning path for owning the architecture at the right
level.

The goal is not to memorize every function. The goal is to build a reliable
mental model of:

- where a run starts
- how the pipeline is shaped
- where learned state lives
- what gets persisted
- what makes a result trustworthy

Use this walk with:

- `../CHART-CONVENTIONS.md`
- `00-study-path.md`

## How To Use This Walk

For each step:

1. read the chart named in the step
2. open the linked code files
3. explain the same idea back in your own words before moving on

If you cannot explain a step simply, do not move forward yet.

## Step 1: Start At The Boundary

Read chart:

- `01-system-overview-dataflow.md`

Read code:

- `api/routes/main.py`
- `api/routes/routes_session.py`

Focus on:

- where HTTP requests become normalized run settings
- where `explore_runtime` is shaped
- where session capture is assembled for review

You should be able to answer:

1. What are the major public surfaces of the system?
2. Where does the API stop and the pipeline begin?
3. Which part is execution, and which part is capture/reporting?

## Step 2: Learn The Canonical Stage Model

Read chart:

- `02-stage-model.md`

Read code:

- `api/pipeline/core/handoff_contract.py`
- `docs/architecture/ARCHITECT-OPERATING-GUIDE.md`

Focus on:

- canonical stage IDs and order
- required inputs and outputs per stage
- transition contracts between stages

You should be able to answer:

1. What is each stage supposed to add?
2. Which stage outputs are later stages expected to consume?
3. Why is `handoff_contract.py` the canonical source of truth for stage semantics?

Important note:

- some session/capture folders still use older historical names in `api/routes/routes_session.py`
- do not let capture layout override the canonical stage model

## Step 3: Understand The Worker Loop

Read chart:

- `01-system-overview-dataflow.md`

Read code:

- `api/pipeline/runner.py`

Focus on:

- `ExploreRuntime` creation
- `ExploreContext` construction
- prior-run loading
- checkpoint loading and stage execution

You should be able to answer:

1. What gets built before the stage pipeline starts?
2. How do prior-job artifacts influence a new run?
3. Where do checkpoint and replay hooks enter the loop?

## Step 4: Separate Run Shape From Learned State

Read chart:

- `04-context-memory-model.md`

Read code:

- `api/pipeline/core/types.py`
- `api/pipeline/s00_setup/context.py`
- `api/pipeline/s02_probe/context.py`

Focus on:

- `ExploreRuntime` versus `ExploreContext`
- what is immutable during a run
- what is mutated as evidence accumulates
- stage-specific context defaults versus shared context state

You should be able to answer:

1. What kind of thing belongs in `ExploreRuntime`?
2. What kind of thing belongs in `ExploreContext`?
3. Which stage families primarily write to which parts of context?

## Step 5: Understand Checkpoints As Memory And Boundaries

Read chart:

- `04-context-memory-model.md`

Read code:

- `api/pipeline/core/checkpoint.py`
- `api/pipeline/core/cluster_checkpoint.py`
- `docs/architecture/CHECKPOINT-SYSTEM.md`

Focus on:

- latest checkpoint versus stage snapshot
- function checkpoints versus stage checkpoints
- cluster checkpoints versus stage checkpoints
- canonical cluster checkpoint fields such as active seam, gate color, trusted
  proof jobs, artifact families, blockers, reuse eligibility, and expected next
  move
- resume boundary behavior
- checkpoint seeding back into context
- how `prior_job_id + focus_functions` can promote into a default cluster seed
  for repeat work
- where `convergence_summary.json` proves whether the next bounded pass became
  cheaper, narrower, or more decisive

You should be able to answer:

1. What can a checkpoint preserve?
2. What does resuming from a stage boundary mean here?
3. Why are checkpoints both archival boundaries and iteration tools?
4. Why would a cluster checkpoint be more reusable than a whole-DLL rerun surface?

## Step 6: Learn How Claims Are Made

Read chart:

- `03-status-classification.md`

Read code:

- `api/pipeline/core/finding_status.py`

Focus on:

- canonical statuses
- normalization of mixed-epoch aliases
- functional-precondition classification versus generic failure

You should be able to answer:

1. How does a raw probe outcome become a canonical claim?
2. Why is `functional_precondition_unmet` stronger than generic `failure`?
3. Why does status normalization matter for comparisons?

## Step 7: Learn How Trust Is Enforced

Read chart:

- `01-system-overview-dataflow.md`

Read code:

- `scripts/harness_lib/collector.py`
- `api/pipeline/core/compatibility.py`
- `api/analysis/blocker_harvest.py`

Focus on:

- contract validation
- stage handoff audit
- transition contract audit
- schema handoff audit
- run validity and ledger append
- lane trust and blocker-harvest classification

You should be able to answer:

1. What keeps the repo from treating raw artifacts as automatically trustworthy?
2. How does the collector turn outputs into audit surfaces?
3. What makes a run promotable versus merely interesting?
4. How does the repo separate measurement failures from real architecture gaps?

## Step 8: Extend Into The Thesis

Once the 4-chart engineering set feels stable, move outward:

- `../02-architecture-thesis-5/05-truth-replay-checkpoints-compounding.md`
- `../03-full-thesis-6-cross-dll/06-campaign-cross-dll-evidence-flow.md`
- `api/pipeline/core/campaign_stages.py`
- `docs/architecture/MVP-THESIS.md`

Focus on:

- replay-backed compounding
- claim boundaries
- campaign planning and consolidation
- where cross-DLL learning actually enters the architecture
- where package metadata, lane gating, and blocker-family summaries enter the campaign layer
- where `campaign-truth.json` and `campaign-attribution-report.json` now expose
  the first explicit `cross_dll_contracts` surface for shared runtime entity
  continuity
- why expansion waves use overlap-baseline comparison instead of assuming
  package-wide comparability
- why clean trust is necessary but not sufficient for architecture selection
- why package expansion is a robustness test on previously trusted overlap,
  not just a larger coverage run

You should be able to answer:

1. Why is replay useful but not identical to cold robustness?
2. How does the repo prevent compounding from becoming fake progress?
3. What makes the cross-DLL layer a real architecture claim instead of just batch execution?
4. What makes a cross-DLL handoff explicit and observer-confirmed instead of implied by seeding alone?
5. Why is package-level blocker harvesting a measurement mode rather than a product autonomy claim?
6. Why can previously verified overlap functions regress when package context gets denser?
7. Why must overlap regressions block promotion even when the expanded wave is internally trusted?

## Minimal Ownership Standard

You are ready to direct work at the right altitude when you can explain, out
loud and without the charts open:

1. the canonical stage model
2. the difference between `ExploreRuntime` and `ExploreContext`
3. where checkpoints sit in the loop
4. where session capture sits in the loop
5. where the collector enforces trust
6. how replay differs from cold-run robustness
7. how package-level campaigns differ from per-DLL truth fixtures
8. why overlap-baseline comparison is required before trusting expansion-wave conclusions
9. why expansion safety requires the overlap slice to survive denser context, not merely remain comparable

If you can do that, you do not need to know every file yet. You know enough to
own the architecture.
