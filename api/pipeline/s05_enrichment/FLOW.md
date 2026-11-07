# S-05: Enrichment + MC-5 — Flow

> **Input:** Synthesis doc, reconciled findings, verified functions
> **Output:** Enriched MCP schema with backfilled parameters, verified descriptions

```mermaid
flowchart TD
    SYNTH["api_reference.md +<br/>Reconciled Findings"] --> BACKFILL["Phase 7: Schema Backfill"]
    BACKFILL -->|"LLM enriches each param<br/>Adds descriptions, types, constraints"| SCHEMA["Enriched MCP Schema"]

    SCHEMA --> VERIFY["Phase 7b: Verification"]
    VERIFY -->|"Lane 1: replay known-good calls<br/>Lane 2: verify stateful mutators<br/>through same-session effects"| VERIFIED["Verification Results"]

    VERIFIED --> MC5{"MC-5: Read-to-Write<br/>Chaining"}

    MC5 -->|"Extract verified read outputs<br/>(customer IDs, amounts)"| VALUES["Known-Good Values"]
    VALUES -->|"Build write fn arg combos<br/>ID × amount × init mode"| COMBOS["Argument Combinations"]
    COMBOS --> TRY["Try each combo on<br/>every write function"]

    TRY --> UNLOCK{Any write<br/>unlocked?}
    UNLOCK -->|Yes| RESOLVED["_mark_unlock_resolved"]
    UNLOCK -->|No| DEFER["Defer to MC-6"]

    RESOLVED --> LIVE["Append to ctx.live_findings<br/>(cross-stage propagation)"]
    LIVE --> S05C["Checkpoint: s05_read_to_write_chaining complete"]
    S05C --> CKPT["Compatibility parent: s05_enrichment complete"]
    DEFER --> CKPT

    CKPT --> S06["→ S-06: Gap Resolution"]

    style SYNTH fill:#1e40af,color:#fff,stroke:#1e40af
    style CKPT fill:#16a34a,color:#fff,stroke:#16a34a
    style S06 fill:#7c3aed,color:#fff,stroke:#7c3aed
    style MC5 fill:#f59e0b,color:#000,stroke:#d97706
    style RESOLVED fill:#22c55e,color:#fff,stroke:#16a34a
    style LIVE fill:#06b6d4,color:#fff,stroke:#0891b2
```

## MC-5: Read-to-Write Chaining

MC-5's key insight: if `CS_GetAccountBalance("CUST-001")` returned success, then "CUST-001" is a confirmed-valid customer ID. Chain it into `CS_ProcessPayment(customer_id="CUST-001", amount=100)`.

This is the "circular enrichment" pattern at its most concrete — read function outputs become write function inputs.

## Circular Enrichment

The enriched schema is the primary deliverable artifact. Each run refines parameter descriptions, constraints, and examples. Verification ensures descriptions match actual DLL behavior, not just LLM hallucination.

## Stateful Mutator Verification

Phase 7b now has two verification lanes:

- direct replay for existing success findings with concrete `working_call` evidence
- stateful mutator verification for near-success setter or writer calls discovered in the probe log

The second lane does not promote custom positive returns by itself. It rebuilds a fresh same-session lineage, runs the mutator, and promotes only when a downstream consumer or observer shows a deterministic effect.
