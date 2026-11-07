# S-06: Gap Resolution + MC-6 — Flow

> **Input:** All findings, enriched schema, all prior MC decisions
> **Output:** Resolved gaps, clarification questions for user, MC-6 comprehensive unlock
> **Next:** S-04 refresh (regenerate synthesis), then S-07 Finalize

```mermaid
flowchart TD
    ALL["All Findings +<br/>Prior MC Decisions"] --> GAP_AGENT["Gap Resolution Agent"]

    GAP_AGENT --> IS_WRITE{"Is write<br/>function?"}
    IS_WRITE -->|Yes| RESTORE["🔄 State Baseline Restoration<br/>1. Call init functions<br/>2. Replay unlock sequence<br/>(BUG-021 fix)"]
    IS_WRITE -->|No| PROBE_DIRECT["LLM agent targets<br/>unverified function"]
    RESTORE --> PROBE_WRITE["LLM agent probes<br/>with conservative amounts<br/>(1, 10, 50 — not 100+)"]

    PROBE_DIRECT --> VALIDATE["Validate Args<br/>(reject placeholders)"]
    PROBE_WRITE --> VALIDATE
    VALIDATE --> GAP_RESULT["Gap Findings"]

    GAP_RESULT --> MC6{"MC-6: Final<br/>Comprehensive Unlock"}

    MC6 --> A["Phase A: LLM Code Reasoning"]
    A -->|"ALL decompiled C<br/>XOR checksums, magic values"| STRAT_A["Code-Derived Strategies"]

    MC6 --> B["Phase B: Pattern-Based Unlock"]
    B -->|"Analyze decompiled unlock patterns<br/>Generate XOR codes"| STRAT_B["XOR + Pattern Combos"]

    MC6 --> C["Phase C: Dependency Chain Replay"]
    C -->|"Call A, then call B<br/>Test write after each"| STRAT_C["Sequence Attempts"]

    MC6 --> D["Phase D: Brute-Force Fallback"]
    D -->|"All IDs × amounts (1,10,50,100)<br/>Last resort"| STRAT_D["Brute-Force Sweep"]

    STRAT_A --> COMBINE["Combine all attempts"]
    STRAT_B --> COMBINE
    STRAT_C --> COMBINE
    STRAT_D --> COMBINE

    COMBINE --> UNLOCK{Any write<br/>unlocked?}
    UNLOCK -->|Yes| RESOLVED["Patch findings<br/>(verified_success)"]
    UNLOCK -->|No| STATUS_CHK{"Business error<br/>(meaningful sentinel)?"}

    STATUS_CHK -->|"Yes (e.g. insufficient points)"| FUNC_STATUS["Mark functional_<br/>precondition_unmet"]
    STATUS_CHK -->|"No (generic error)"| QUESTIONS["Generate clarification<br/>questions for user"]

    RESOLVED --> LIVE["→ ctx.live_findings"]
    FUNC_STATUS --> LIVE
    LIVE --> S04R["S-04 Refresh:<br/>Regenerate api_reference.md<br/>(with MC-6 findings)"]
    QUESTIONS --> S04R

    S04R --> CKPT["Checkpoint: s06_gaps complete"]
    CKPT --> S07["→ S-07: Finalize"]

    style ALL fill:#1e40af,color:#fff,stroke:#1e40af
    style CKPT fill:#16a34a,color:#fff,stroke:#16a34a
    style S07 fill:#7c3aed,color:#fff,stroke:#7c3aed
    style MC6 fill:#f59e0b,color:#000,stroke:#d97706
    style RESOLVED fill:#22c55e,color:#fff,stroke:#16a34a
    style QUESTIONS fill:#ef4444,color:#fff,stroke:#dc2626
    style LIVE fill:#06b6d4,color:#fff,stroke:#0891b2
    style RESTORE fill:#f97316,color:#fff,stroke:#ea580c
    style IS_WRITE fill:#8b5cf6,color:#fff,stroke:#7c3aed
    style FUNC_STATUS fill:#0891b2,color:#fff,stroke:#0891b2
    style STATUS_CHK fill:#8b5cf6,color:#fff,stroke:#7c3aed
```

## MC-6: Final Comprehensive Unlock

MC-6 is the most powerful coordinator. It has the richest context:
- All probe findings from S-02
- All MC-3/MC-4/MC-5 decisions and their outcomes
- Full decompiled C code
- Complete sentinel catalog (with function-scoped meanings)

It runs 4 phases in sequence, from most targeted to broadest sweep.

### `functional_precondition_unmet` Classification

When MC-6 cannot unlock a function but the return value is a **business-logic sentinel** (e.g. "insufficient points", "balance too low") and the call shape is valid, the finding is classified as `functional_precondition_unmet` — not `failure`. This status counts toward `discovered_rate` and signals the function works but runtime state is unsatisfied.

If the error is truly generic (access denied, not initialized), the pipeline generates clarification questions instead.

### S-04 Refresh

After MC-6, the runner re-invokes S-04 synthesis to regenerate `api_reference.md` with post-gap findings, avoiding a stale document that says "no working init found" when MC-6 already solved it.

## Circular Enrichment

MC-6's clarification questions are surfaced in the UI. When the user answers them, the answers feed into the next pipeline run as additional context. MC-6's decision history is also persisted, so subsequent runs know what was already tried and can avoid redundant work.
