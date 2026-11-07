# S-07: Finalize — Flow

> **Input:** All findings, enriched schema, MC decisions, synthesis doc
> **Output:** Final harmonized schema, behavioral spec, Python wrapper, macro verdict, contract artifacts, floor-to-ceiling iteration artifacts when enabled, and package-frontier artifacts for package-floor campaigns

```mermaid
flowchart TD
    ALL["All Enriched Findings"] --> HARMONIZE["Harmonization"]
    HARMONIZE -->|"Deduplicate findings<br/>Resolve conflicts<br/>Best-of-N selection"| FINAL["Harmonized Findings"]

    FINAL --> BEHAV["Behavioral Spec Generation"]
    BEHAV -->|"LLM generates Python class<br/>with typed methods + docstrings"| SPEC["behavioral_spec.py"]

    FINAL --> SCHEMA["Final MCP Schema"]
    SCHEMA -->|"JSON tool definitions<br/>with enriched param descriptions"| MCP["mcp_schema.json"]

    SPEC --> FINALIZE["Finalize<br/>(vocab description, AC-4 closure)"]
    MCP --> FINALIZE

    FINALIZE --> CONTRACT["emit_contract_artifacts<br/>(best-effort async finally)"]
    FINALIZE --> FLOOR["floor_plan.json<br/>prerequisite_state_groups.json<br/>ceiling_frontier.json<br/>floor_iteration_state.json<br/>package-frontier-plan.json"]
    CONTRACT -->|"session-meta.json<br/>stage-index.json<br/>transition-index.json<br/>cohesion-report.json"| CONTRACT_OK["Contract Blobs Written"]

    CONTRACT_OK --> MACRO["Macro Coordinator: evaluate_run()<br/>(verified/discovered + floor verdict)"]
    FLOOR --> MACRO

    MACRO --> VERDICT{Verdict}
    VERDICT -->|"verified ≥ 85%<br/>OR discovered ≥ 95%"| DONE["✅ done"]
    VERDICT -->|"open questions"| CLARIFY["❓ awaiting_clarification"]
    VERDICT -->|"below thresholds"| LOOP["🔄 loop_again"]

    DONE --> PERSIST["persist_verdict()"]
    CLARIFY --> PERSIST
    LOOP --> PERSIST

    PERSIST -->|"macro_verdict.json<br/>+ job status update"| END["Pipeline Complete"]

    END -->|"If loop_again"| NEXT["Next Run<br/>(with strategy_adjustments<br/>+ variant_configs)"]
    END -->|"If awaiting_clarification"| UI["UI: Show Questions"]
    END -->|"If done"| DELIVER["Deliverables Ready:<br/>Schema + Spec + Docs"]

    style ALL fill:#1e40af,color:#fff,stroke:#1e40af
    style DONE fill:#22c55e,color:#fff,stroke:#16a34a
    style CLARIFY fill:#f59e0b,color:#000,stroke:#d97706
    style LOOP fill:#eab308,color:#000,stroke:#ca8a04
    style DELIVER fill:#7c3aed,color:#fff,stroke:#7c3aed
    style CONTRACT fill:#0891b2,color:#fff,stroke:#0891b2
```

## Contract Artifact Emission

`emit_contract_artifacts` runs in a **best-effort asynchronous `finally`** block so the four contract JSON files are attempted even if harmonize or finalize raises partway through. Contract-artifact emission is surfaced through the `s07_emit_contract_artifacts` span and immediately deferred so terminal worker close is not blocked. The runner's **error handler** also performs a best-effort emission on fatal explore errors, so nightly ZIPs and save-session v2 can still validate transitions for post-mortems.

S-07 component-description synthesis is optional close-path enrichment. The
live default is deterministic description text. Opt-in model synthesis is
bounded at the stage layer and may degrade if the model client stalls; that
must not block final vocab persistence, schema-evolution evidence, or macro
verdict persistence.

Contract files required by `collect_session.py` (save-session v2):
- `session-meta.json` — job identity, timestamps, counts, profile
- `stage-index.json` — per-stage status, artifacts, errors
- `transition-index.json` — 18+ transition pass/fail records
- `cohesion-report.json` — gate results, summary, hard_fail flag

When `iteration_mode=floor_to_ceiling`, S-07 also persists:
- `floor_plan.json` â€” active floor scope, prerequisite-state groups, protected truths, and ceiling
- `prerequisite_state_groups.json` â€” resolved prerequisite bootstrap groups for the cycle
- `ceiling_frontier.json` â€” previous and next ceiling frontier
- `floor_iteration_state.json` â€” preservation verdict, carryover status, and next-cycle recommendation

When the active floor is `package`, the canonical package-facing artifact is:

- `package-frontier-plan.json` - imported lower-floor DLL truth, active package frontier, frontier entries, and package-floor observer contracts

Legacy `batch-b-ceiling-plan.json` remains a compatibility artifact for older sessions and transitional readers.

If floor broadening is intentionally blocked, S-07 still emits contract and
package artifacts with a valid `stage-index.json` skip explanation instead of
forcing the run to look degraded.

## Macro Coordinator Verdict

The macro coordinator runs deterministic rules using the **status taxonomy**:

| Coverage | Questions? | Verdict | Next Action |
|----------|-----------|---------|-------------|
| `verified_rate` ≥ 85% | — | `done` | Deliver artifacts |
| `discovered_rate` ≥ 95% | — | `done` | Remaining gaps are precondition-only |
| Any | Yes | `awaiting_clarification` | Show questions in UI |
| Below thresholds | No | `loop_again` | Suggest strategy adjustments + variant configs |

**Strategy adjustments** for `loop_again`:
- `focus_functions`: Top unresolved functions (up to 6)
- `skip_to_stage`: Skip setup/unlock if already resolved
- `focus_write_unlock`: Write-type failures detected → expand sweep
- DLL entry points (`entry`, `DllMain`) excluded from coverage calculation

## Circular Enrichment

The verdict and strategy adjustments are stored in the checkpoint. The UI's "Re-run with suggestions" button pre-fills explore settings from the verdict, enabling one-click circular enrichment.

## Full Pipeline Summary

```
DLL Binary
    ↓
S-00: Setup (sentinels, vocab, static analysis, call graph, data types)
    ↓
S-01: Write-Unlock Probe (code reasoning, init sweep)
    ↓
S-02: Probe Loop (per-function LLM agent; M=2 variants via SFP when enabled)
    ↓
S-03: Reconcile + MC-3 (write failure classification, function-scoped sentinel catalog)
    ↓
S-04: Synthesis + MC-4 (API reference, init clues)
    ↓
S-05: Enrichment + MC-5 (backfill, verify, read→write chain)
    ↓
S-06: Gap Resolution + MC-6 (comprehensive unlock, functional_precondition_unmet)
    ↓
S-04 refresh: Regenerate synthesis with post-gap findings
    ↓
S-07: Finalize (harmonize, behavioral spec, contract emission, verdict)
    ↓
Deliverables: mcp_schema.json + behavioral_spec.py + api_reference.md
              + session-meta / stage-index / transition-index / cohesion-report
```
