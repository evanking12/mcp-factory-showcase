# System Register And Purpose

This chart answers a different question than the stage charts.

- stages explain **when** work happens
- systems explain **what reusable mechanism** is doing the work

```mermaid
flowchart TD
    A["1. Static Discovery Intake<br/>Discovers exports, parameters, and initial callable surface"] --> B["2. Finding-Status Taxonomy And Normalization<br/>Turns raw outcomes into canonical statuses"]
    B --> C["3. Evidence-Candidate Tiering And Ranking<br/>Ranks generic, static, runtime, and carry-forward argument candidates"]
    C --> D["4. Checkpoint, Replay, And Carry-Forward Compounding<br/>Persists trusted state and reuses it across runs"]
    C --> E["5. Gap-Resolution And Late Retry<br/>Retries unresolved functions with better context and targeted plans"]
    D --> E
    D --> F["6. Campaign Evidence Graph And Planning<br/>Connects runs and DLLs into a cross-DLL learning surface"]
    C --> G["7. Runtime Artifact Materializer (First Wave)<br/>Captures produced IDs, handles, tokens, and output-derived state for reuse"]
    G --> E
    G --> F
    H["8. Lab Validity And Monitoring<br/>Verifies that the API, bridge, model path, and lane are trustworthy"] --> E
    H --> F
    I["9. Session, Ledger, And Review Capture Surfaces<br/>Makes runs reviewable, auditable, and comparable by a human"] --> F
    E --> I
```

## Reading Note

The important architectural point is overlap:

- a stage can involve multiple systems
- a system can span multiple stages

That overlap is expected when the system is layered rather than redundant.

## Current Interpretation

The most important active Tier 1 system is still:

- `runtime artifact materializer`

But it sits on top of older systems rather than replacing them.
