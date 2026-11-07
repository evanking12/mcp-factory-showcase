# Session Capture vs Canonical Stages

Primary code anchors:

- `api/pipeline/core/handoff_contract.py`
- `api/routes/routes_session.py`

```mermaid
flowchart TB
    subgraph Canonical["Canonical stage model"]
        S00["S-00 setup"]
        S01["S-01 write-unlock"]
        S02["S-02 probe-loop"]
        S03["S-03 reconcile"]
        S04["S-04 synthesis"]
        S05["S-05 enrichment"]
        S06["S-06 gap-resolution"]
        S04R["S-04R synthesis-refresh"]
        S07["S-07 finalize"]
    end

    subgraph Session["Session snapshot compatibility surface"]
        L00["stage-00-setup/"]
        L01["stage-01-probe-loop/"]
        L02["stage-02-synthesis/"]
        L03["stage-03-gap-resolution/"]
        L04["stage-04-clarification/"]
        L05["stage-05-finalization/"]
    end

    S00 --> L00
    S01 --> L00
    S02 --> L01
    S02 -. "findings reused" .-> L02
    S04 --> L02
    S05 --> L02
    S06 --> L03
    S04R -. "review surface only" .-> L04
    S07 --> L05

    Canonical --> IDX["stage-index.json"]
    Canonical --> CSM["canonical-stage-model.json"]
    Session --> ALIAS["capture-layout-stage-aliases.json"]
```

Interpretation:

- The semantic stage model is `S-00` through `S-07`.
- The `stage-xx-*` folders in a saved session are compatibility layout, not the stage contract.
- `stage-04-clarification/` is a review surface, not a canonical pipeline stage.
- When a chart and a session folder disagree, trust the canonical stage model and the alias metadata.
- `stage-index.json` is also the canonical place to explain an intentional
  floor-gated skip such as `floor_broadening_blocked`; capture validity should
  follow that contract explanation rather than assume every skipped broadening
  stage is a failure.
- Schema-handoff and transition audits must ignore compatibility snapshots and
  edges owned by those intentionally skipped stages; otherwise floor-gated runs
  will be misclassified as regressions even when the skip contract is honest.
