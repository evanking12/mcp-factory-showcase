# S-05 — Enrichment

## Purpose

S-05 **verifies** and **enriches** the model of the DLL. **Backfill** pulls parameter descriptions from the synthesis document and patches them into the schema. **Verification** re-executes every “success” finding’s `working_call` against the live DLL to confirm it returns success (e.g. 0). **MC-5** chains **verified read** outputs into **write** arguments (e.g. if `CS_GetAccountBalance("CUST-001")` is proven, reuse `"CUST-001"` in `CS_ProcessPayment`).

## What it discovers

- **Schema enrichment**: parameters and types grounded in the synthesis text.
- **Execution-backed confirmation** of successful calls.
- **Cross-call data flow** suggestions linking reads to writes when evidence supports it.

## How it feeds the circular enrichment pattern

**Verified** findings are **higher confidence** than purely inferred ones—this distinction is the practical differentiator (“we prove it”). Run N+1 starts with that proof layer already attached, shrinking the ambiguous set faster.

## Dependencies (what it needs from prior stages)

- **S-04**: synthesis document and derived structure.
- **S-03** (and below): reconciled findings and working calls to verify and extend.

## Non-goals

- S-05 does not perform first-pass discovery.
- S-05 does not own final gap retries.
- S-05 does not claim full proof when verification coverage is partial.
