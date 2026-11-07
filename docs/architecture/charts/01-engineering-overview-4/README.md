# 4-Chart Engineering Overview

Use this set when the goal is to understand what the code does without pulling
in the full product thesis.

This is the canonical source set. Refine these charts first, then mirror
important changes into the 5-chart and 6-chart sets.

Start with:

1. `ARCHITECTURE-WALK.md`
2. `00-study-path.md`

Recommended charts:

1. System overview and dataflow
2. Stage model
3. Status and classification
4. Context and memory model

This set should stay implementation-grounded and map closely to pipeline,
contract, and collector behavior.

Suggested study order:

1. `01-system-overview-dataflow.md`
2. `02-stage-model.md`
3. `04-context-memory-model.md`
4. `03-status-classification.md`

Optional support chart:

- `05-session-capture-canonical-stage-map.md`
  - Use this when reading session bundles so the legacy capture folders are not
    mistaken for the canonical stage model.

If you are trying to own the architecture, do not just read the charts. After
each one, explain the same idea back in your own words using the linked code
anchors in that file.
