# S-03: Reconcile + MC-3 — Flow

> **Input:** Raw probe findings from S-02 (or merged findings from Variant Merger when M > 1)
> **Output:** Reconciled findings, write failure classification, sentinel catalog

```mermaid
flowchart TD
    FINDINGS["Raw / Merged Probe Findings"] --> RECONCILE["Reconciliation"]
    RECONCILE -->|"Merge duplicate findings<br/>Resolve conflicting statuses<br/>Best-call selection"| CLEAN["Reconciled Findings"]

    CLEAN --> MC3{"MC-3: Write Failure<br/>Classification"}

    MC3 -->|"Uniform sentinel<br/>(init problem)"| SWEEP["Targeted Init Sweep<br/>modes 0-64"]
    MC3 -->|"Mixed sentinels"| CLASSIFY["Classify init-blocked<br/>vs arg-blocked"]
    CLASSIFY -->|"Init-blocked fns"| PARTIAL_SWEEP["Partial Init Sweep"]
    CLASSIFY -->|"All arg-blocked"| DEFER["Defer to MC-4/5/6"]
    PARTIAL_SWEEP --> UNLOCK
    MC3 -->|"Accidental success"| PATCH["Patch finding → verified_success"]
    MC3 -->|"No write probes"| REPROBE["Full write re-probe"]

    SWEEP --> UNLOCK{Unlocked?}
    UNLOCK -->|Yes| RESOLVED["_mark_unlock_resolved"]
    UNLOCK -->|No| DEFER

    RESOLVED --> LIVE_A["Append to ctx.live_findings"]
    PATCH --> LIVE_B["Append to ctx.live_findings"]
    LIVE_A --> CATALOG["Sentinel Catalog"]
    LIVE_B --> CATALOG
    DEFER --> CATALOG
    REPROBE --> CATALOG

    CATALOG -->|"Per-function business-logic labels<br/>e.g. 0xFB on ProcessPayment =<br/>'insufficient funds'"| NAMED["Named Sentinel Catalog<br/>(function-scoped meanings)"]

    NAMED --> CKPT["Checkpoint: s03_reconcile complete"]
    CKPT --> S04["→ S-04: Synthesis"]

    style FINDINGS fill:#1e40af,color:#fff,stroke:#1e40af
    style CKPT fill:#16a34a,color:#fff,stroke:#16a34a
    style S04 fill:#7c3aed,color:#fff,stroke:#7c3aed
    style MC3 fill:#f59e0b,color:#000,stroke:#d97706
    style RESOLVED fill:#22c55e,color:#fff,stroke:#16a34a
    style LIVE_A fill:#06b6d4,color:#fff,stroke:#0891b2
    style LIVE_B fill:#06b6d4,color:#fff,stroke:#0891b2
```

## MC-3: Post-Reconcile Write Failure Classification

MC-3 is the first micro coordinator to run. It classifies the pattern of write failures:

| Pattern | Diagnosis | Action |
|---------|-----------|--------|
| All write fns return same error | Init/auth problem | Targeted sweep |
| Different errors per function | Classify init-blocked vs arg-blocked | Partial sweep + defer |
| Write fn returned 0 (success) | Recording error, not actual failure | Patch finding → `verified_success` |
| No write probes attempted | Curriculum skipped writes | Re-probe |

## Sentinel Catalog — Function-Scoped Semantics

The same numeric sentinel may mean different things on different exports (BUG-031). The catalog should store **per-function** labels where needed:
- `0xFFFFFFFB` on `ProcessPayment` → "insufficient funds"
- `0xFFFFFFFB` on `RedeemLoyaltyPoints` → "insufficient loyalty points (business precondition)"

This distinction feeds into `functional_precondition_unmet` classification downstream.

## Circular Enrichment

The sentinel catalog names become part of the LLM context for future runs. Instead of seeing `returned 0xFFFFFFFB`, the LLM sees a business-logic label — much more informative for reasoning about how to proceed.
