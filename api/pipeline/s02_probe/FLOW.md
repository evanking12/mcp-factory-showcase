# S-02: Probe Loop — Flow

> **Input:** ExploreContext with sentinels, vocab, unlock status, call graph, data types
> **Output:** Per-function findings (call results, return codes, parameter semantics)
> **NxM:** M=2 in Phase 1 (Explorer + Creative variants); M=1 fallback identical to legacy.

```mermaid
flowchart TD
    CTX["ExploreContext + Unlock Status"] --> S02A["S-02A: probe_ordering"]
    S02A --> CURRICULUM["Curriculum Ordering"]
    CURRICULUM -->|"Topological sort via call graph<br/>Callees before callers<br/>Init first, writes last"| ORDER["Ordered Function Queue"]

    ORDER --> S02B["S-02B: invocation_execution"]
    S02B --> VRUNNER{"M > 1?"}
    VRUNNER -->|"Yes (NxM)"| SPAWN["Variant Runner<br/>spawn M bridges + M contexts"]
    VRUNNER -->|"No (legacy)"| LOOP

    SPAWN --> VA["Variant A (Explorer)<br/>o4-mini, t=0, full ctx, topo order"]
    SPAWN --> VB["Variant B (Creative)<br/>o4-mini, t=0.3, minimal ctx, random order"]

    VA --> VA_LOOP["Per-Function LLM Probe"]
    VB --> VB_LOOP["Per-Function LLM Probe"]

    VA_LOOP -->|publish| SFP["Shared Findings Pool<br/>(cross-variant, real-time)"]
    VB_LOOP -->|publish| SFP
    SFP -->|"snapshot before next fn"| VA_LOOP
    SFP -->|"snapshot before next fn"| VB_LOOP

    VA_LOOP --> VA_DONE["Variant A done"]
    VB_LOOP --> VB_DONE["Variant B done"]
    VA_DONE --> VMERGE["Variant Merger<br/>(best-per-fn, status hierarchy)"]
    VB_DONE --> VMERGE
    VMERGE --> MERGED["Merged Findings<br/>+ variant_contributions.json"]
    MERGED --> S02C["S-02C: evidence_capture"]

    subgraph LOOP["Per-Function Probe (single variant or M=1)"]
        direction TB
        FN["Pick next function"]
        FN --> CONF_CHK{"Decompiler<br/>confidence?"}
        CONF_CHK -->|"Low (< 0.5)"| WARN["Inject confidence warning"]
        CONF_CHK -->|"Normal"| PROMPT
        WARN --> PROMPT["Build LLM prompt<br/>(system + fn schema + vocab +<br/>sentinels + data types)"]
        PROMPT --> AGENT["LLM Agent (tool-calling)"]
        AGENT -->|"Calls DLL via tool_call"| EXEC["Execute on Bridge"]
        EXEC --> RESULT["Return code + output"]
        RESULT --> INTERPRET["LLM interprets result"]
        INTERPRET --> FINDING["record_finding<br/>(status hierarchy)"]
        FINDING --> LIVE["→ ctx.live_findings / SFP"]
        LIVE --> MORE{More fns?}
        MORE -->|Yes| FN
        MORE -->|No| DONE["Variant complete"]
    end

    DONE --> S02C
    S02C --> RECALIB["Sentinel Recalibration"]
    RECALIB --> CKPT["Checkpoint: s02_evidence_capture + s02_probe compatibility parent complete"]
    CKPT --> S03["→ S-03: Reconcile"]

    style CTX fill:#1e40af,color:#fff,stroke:#1e40af
    style CKPT fill:#16a34a,color:#fff,stroke:#16a34a
    style S02A fill:#0f766e,color:#fff,stroke:#0f766e
    style S02B fill:#0f766e,color:#fff,stroke:#0f766e
    style S02C fill:#0f766e,color:#fff,stroke:#0f766e
    style S03 fill:#7c3aed,color:#fff,stroke:#7c3aed
    style AGENT fill:#f59e0b,color:#000,stroke:#d97706
    style SFP fill:#7c3aed,color:#fff,stroke:#a78bfa
    style VMERGE fill:#059669,color:#fff,stroke:#10b981
    style SPAWN fill:#7c3aed,color:#fff,stroke:#7c3aed
```

## Key Decisions at This Stage

- **Runtime split identity**: S-02 now exposes `s02_probe_ordering`,
  `s02_invocation_execution`, and `s02_evidence_capture` while preserving
  `s02_probe` as the full-stage compatibility parent.
- **Curriculum ordering** uses topological sort on the call graph when available. Callees are probed before callers so their working calls are in `live_findings` first. Falls back to uncertainty score when no call graph exists.
- **Prerequisite-state groups** sit next to functional clusters. They do not replace curriculum ordering; they bound which prerequisite bootstrap surfaces are seeded and observed during floor-to-ceiling iteration.
- **NxM variant runner** (Phase 1 locked: M=2): spawns two bridge instances and two `ExploreContext` copies sharing a `SharedFindingsPool`. Until BUG-028 + bridge isolation land, runs sequential pseudo-M or M=1.
- **Shared Findings Pool (SFP)**: cross-variant real-time store. When Variant B discovers a working init, Variant A sees it on its next function probe. Publishes with the full status hierarchy.
- **Variant Merger**: after all variants finish, selects the best finding per function (`verified_success > functional_precondition_unmet > inferred_success > failure > unknown`). Writes `variant_contributions.json`.
- **Decompiler confidence warnings** inject a warning into the LLM prompt when Ghidra's confidence is low (< 0.5).
- **Data types in system message** — structs, enums, typedefs from Ghidra's DTM.
- **Per-function budget** is controlled by `max_rounds` and `max_tool_calls`.
- **Intra-stage finding propagation** (`live_findings` / SFP): function A's success is immediately available to function B within the same variant (and cross-variant via SFP).
- **Direct target truth provenance**: when probe reaches the right target call,
  the stage now preserves canonical `direct_target_truth` so later verification
  and harmonization do not need to reconstruct the strongest truth only from
  raw probe logs.
- **Sentinel recalibration** at stage boundary catches state changes from probing.

## Circular Enrichment

Prior run findings are loaded as context — the LLM sees what worked before and skips already-verified functions. The probe loop is the primary data-generation stage; all downstream stages consume its findings. **Within a single run**, `live_findings` (or SFP) ensures discoveries propagate forward immediately.
