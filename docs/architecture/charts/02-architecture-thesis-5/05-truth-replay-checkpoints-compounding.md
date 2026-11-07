# Truth, Replay, Checkpoints, And Compounding

Primary code anchors:

- `api/pipeline/core/checkpoint.py`
- `scripts/harness_lib/collector.py`
- `docs/architecture/ARCHITECT-OPERATING-GUIDE.md`
- `docs/architecture/MVP-THESIS.md`

```mermaid
flowchart TD
    COLD["Cold run<br/>generic starting context"] --> RUN1["Pipeline run"]
    RUN1 --> ART1["Artifacts plus findings plus reports"]
    ART1 --> AUDIT1["Collector audits contract and validity"]
    AUDIT1 --> LEDGER1["Run ledger row"]
    ART1 --> CKPT1["Checkpoint snapshots"]

    CKPT1 --> REPLAY["Replay-backed or focused run"]
    LEDGER1 --> REPLAY
    REPLAY --> RUN2["Next pipeline run with prior evidence"]
    RUN2 --> ART2["New artifacts and findings"]
    ART2 --> AUDIT2["Audit again"]
    AUDIT2 --> COMPARE["Compare runs and decide"]

    COMPARE --> GAIN{"Real gain?"}
    GAIN -- "yes, no regression" --> PROMOTE["Promote or keep as stronger baseline"]
    GAIN -- "no, hidden variable or contradiction" --> STOP["Do not overclaim; investigate or stop"]

    subgraph TruthBoundaries["Claim boundaries"]
        T1["Cold robustness"]
        T2["Replay-backed compounding"]
        T3["Promotion-safe audited result"]
    end

    COLD --> T1
    REPLAY --> T2
    PROMOTE --> T3
```

Interpretation:

- Replay-backed gains are real, but they are not the same claim as cold robustness.
- Checkpoints are both resume primitives and archival truth boundaries.
- Audits and ledger rows are what keep compounding from collapsing into fake progress.
