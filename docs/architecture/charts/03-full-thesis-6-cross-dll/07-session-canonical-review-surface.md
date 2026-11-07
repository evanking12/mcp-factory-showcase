# Session Review Surface vs Canonical Stages

Primary code anchors:

- `api/pipeline/core/handoff_contract.py`
- `api/routes/routes_session.py`
- `scripts/harness_lib/collector.py`

```mermaid
flowchart LR
    S["Canonical stages<br/>S-00..S-07"] --> E["evidence/"]
    S --> IDX["stage-index.json"]
    S --> CSM["canonical-stage-model.json"]

    E --> SNAP["session snapshot ZIP"]
    IDX --> SNAP
    CSM --> SNAP

    SNAP --> LEG["legacy stage-xx-* folders"]
    SNAP --> ALIAS["capture-layout-stage-aliases.json"]
    SNAP --> REVIEW["human review / collector / charts"]

    LEG -. "compatibility only" .-> REVIEW
    ALIAS --> REVIEW
```

Interpretation:

- The snapshot is a review bundle, not the source of truth for stage semantics.
- The canonical model should drive charts, explanations, and future architecture work.
- The legacy session folders remain useful for compatibility, but they should be read through the alias map.
