# System Overview And Dataflow

Primary code anchors:

- `api/pipeline/runner.py`
- `api/pipeline/core/handoff_contract.py`
- `api/pipeline/core/checkpoint.py`
- `api/routes/routes_session.py`
- `scripts/harness_lib/collector.py`

```mermaid
flowchart TD
    A["Client or harness starts analysis and explore job"] --> B["API job status stores explore_runtime"]
    B --> C["runner.py builds ExploreRuntime and ExploreContext"]
    C --> D["Pipeline stages execute in order"]

    subgraph Pipeline["Canonical stage pipeline"]
        D1["S-00 setup"]
        D2["S-01 write-unlock"]
        D3["S-02 probe-loop"]
        D4["S-03 reconcile"]
        D5["S-04 synthesis"]
        D6["S-05 enrichment"]
        D7["S-06 gap-resolution"]
        D8["S-04R synthesis-refresh"]
        D9["S-07 finalize"]
        D1 --> D2 --> D3 --> D4 --> D5 --> D6 --> D7 --> D8 --> D9
    end

    D --> E["Evidence artifacts written to blob storage"]
    E --> F["session-snapshot endpoint assembles stage-based capture"]
    E --> G["collector validates contract, stage handoffs, transitions, schema evolution"]
    E --> H["checkpoint system saves latest, per-stage, and cluster snapshots"]

    G --> I["run-validity and kpi_run"]
    G --> J["validation report and artifact index"]
    G --> K["dashboard row and human summaries"]
    G --> L["run ledger append"]

    H --> M["Later run can load checkpoint and resume or focus"]
    F --> N["Human review and saved session archive"]
    I --> N
    J --> N
    K --> N
    L --> O["compare-runs, triage, promotion decisions<br/>(package-floor overlap claims require confirmation-grade evidence)"]

    P["Prior job artifacts and findings"] --> C
    P --> M
    M --> C
```

Notes:

- The chart uses the canonical stage sequence from `handoff_contract.py`.
- Session capture in `routes_session.py` still exposes some older stage folder names; treat that as a capture layout detail, not the canonical stage model.
- `S-05 enrichment` now includes both direct replay verification and same-session effect verification for stateful mutators with custom positive returns.
- Floor-to-ceiling package mode adds a package-frontier planning surface that
  can import lower-floor DLL truth and narrow live work to an active package
  frontier.
- Strict collection is contract-aware: an intentionally skipped broadening
  stage is valid when `stage-index.json` records an allowed floor-gated
  `skip_reason`.
