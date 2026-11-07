# S-01: Write-Unlock Probe — Flow

> **Input:** Foundational context from S-00 (sentinels, vocab, decompiled C)
> **Output:** Write-unlock status (resolved or deferred)

```mermaid
flowchart TD
    CTX["ExploreContext from S-00"] --> CLASSIFY["Classify Functions"]
    CLASSIFY -->|"Identify write-type fns<br/>(pay, redeem, update, create)"| WRITE_FNS["Write Function List"]

    WRITE_FNS --> CODE_REASON["LLM Code Reasoning"]
    CODE_REASON -->|"Analyze decompiled C<br/>Look for init/auth guards"| STRATEGIES["Unlock Strategies<br/>(init modes, auth sequences)"]

    STRATEGIES --> SWEEP["Init Mode Sweep"]
    SWEEP -->|"Try init modes 0-64<br/>Test write fn after each"| RESULT{Unlock<br/>succeeded?}

    RESULT -->|Yes| RESOLVED["Mark write_unlock_block = RESOLVED"]
    RESULT -->|No| DEFERRED["Defer to MC-3 through MC-6"]

    RESOLVED --> REPROBE["Re-probe all write fns<br/>with unlocked context"]
    REPROBE --> CKPT["Checkpoint: s01_unlock complete"]
    DEFERRED --> CKPT

    CKPT --> S02["→ S-02: Probe Loop"]

    style CTX fill:#1e40af,color:#fff,stroke:#1e40af
    style CKPT fill:#16a34a,color:#fff,stroke:#16a34a
    style S02 fill:#7c3aed,color:#fff,stroke:#7c3aed
    style RESOLVED fill:#22c55e,color:#fff,stroke:#16a34a
    style DEFERRED fill:#eab308,color:#000,stroke:#ca8a04
```

## Key Decisions at This Stage

- **Admitted S-00 slice first** reads the S-00 handoff packet when present and
  admits the narrowed `baseline_truth`, `surface_inventory`, and advisory
  `s01_targets` slice before probing.
- **Legacy fallback** keeps using existing `ctx.dll_strings`, `ctx.vocab`, and
  `ctx.sentinels` if the handoff packet is missing, thin, or malformed.
- **Write vs. read classification** uses function name heuristics (pay, process, redeem, update, set, create = write-type).
- **LLM code reasoning** reads the decompiled C to find init guards (`if (!g_initialized) return ERROR`).
- **Init sweep** systematically tries mode values. If a single mode unlocks writes, it's recorded for all downstream stages.

`s01_targets` is advisory in the current live contract. It improves input
organization by moving admitted targets earlier in probe order, but it does not
yet redesign the full unlock planner.

## Circular Enrichment

On subsequent runs, if the prior checkpoint already has `write_unlock_block = RESOLVED`, this entire stage is skipped. The unlock mode value is carried forward in the checkpoint, saving significant runtime.
