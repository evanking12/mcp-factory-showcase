# S-04: Synthesis + MC-4 — Flow

> **Input:** Reconciled findings, sentinel catalog
> **Output:** API reference document, init sequence clues

```mermaid
flowchart TD
    FINDINGS["Reconciled Findings +<br/>Sentinel Catalog"] --> SYNTH["Phase 6: API Reference Synthesis"]
    SYNTH -->|"LLM reads ALL findings<br/>Generates api_reference.md"| DOC["api_reference.md<br/>(comprehensive API doc)"]

    DOC --> MC4{"MC-4: Init Sequence<br/>Clue Extraction"}

    MC4 -->|"Regex parse synthesis doc<br/>Look for init mode mentions"| MODES["Init Mode Candidates"]
    MC4 -->|"Look for dependency chains<br/>('must call X before Y')"| DEPS["Dependency Chains"]

    MODES --> TRY["Try each init mode<br/>via _targeted_unlock_attempt"]
    TRY --> UNLOCK{Unlocked?}
    UNLOCK -->|Yes| RESOLVED["_mark_unlock_resolved"]
    UNLOCK -->|No| LOG_DEPS["Log deps for MC-5/6"]
    DEPS --> LOG_DEPS

    RESOLVED --> CKPT["Checkpoint: s04_synthesis complete"]
    LOG_DEPS --> CKPT

    CKPT --> S05["→ S-05: Enrichment"]

    style FINDINGS fill:#1e40af,color:#fff,stroke:#1e40af
    style CKPT fill:#16a34a,color:#fff,stroke:#16a34a
    style S05 fill:#7c3aed,color:#fff,stroke:#7c3aed
    style MC4 fill:#f59e0b,color:#000,stroke:#d97706
    style RESOLVED fill:#22c55e,color:#fff,stroke:#16a34a
```

## MC-4: Post-Synthesis Init Sequence Clues

MC-4 mines the LLM-generated synthesis document for unlock hints. The synthesis doc often contains phrases like:
- "Initialize with mode 2 to enable write operations"
- "CS_ProcessPayment requires CS_Initialize to be called first"

MC-4 extracts these programmatically and tests them.

## Circular Enrichment

The `api_reference.md` becomes a cumulative document. On subsequent runs, the synthesis incorporates prior-run findings, making it progressively richer. MC-4's discovered init modes feed back into S-01's checkpoint for future runs.
