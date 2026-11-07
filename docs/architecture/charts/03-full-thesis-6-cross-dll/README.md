# 6-Chart Full Thesis Overview

Use this set when the goal is to explain the full thesis, including campaign
learning and cross-DLL interweave.

This set should inherit the core chart vocabulary and stage naming from:

- `../CHART-CONVENTIONS.md`
- `../01-engineering-overview-4/`

Recommended charts:

1. System overview and dataflow
2. Stage model
3. Status and classification
4. Context and memory model
5. Truth, replay, checkpoints, and compounding
6. Campaign and cross-DLL evidence flow

Current leading implementation target:

- the Tier 1 generalized runtime artifact materializer
- use charts 1, 4, and 5 when explaining where that system fits before and
  after the pipeline stages

The sixth chart should stay thesis-level until cross-DLL coordination and
campaign evidence surfaces are stable enough to document more concretely.

Optional support chart:

- `07-session-canonical-review-surface.md`
  - Use this when explaining why the session ZIP and the canonical stage model
    are related but not identical surfaces.
- `08-system-register-and-purpose.md`
  - Use this when explaining what each major system actually does.
- `09-stage-system-correlation.md`
  - Use this when explaining how the stage ladder and the system register
    overlap without meaning the same thing.
