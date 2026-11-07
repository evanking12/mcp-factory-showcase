# S-04 — Synthesis

## Purpose

S-04 **synthesizes** all accumulated evidence into **human-readable API documentation**. The LLM receives every finding, vocabulary entry, and sentinel code, then produces a comprehensive API reference. **MC-4** parses that synthesis for **init-sequence clues** the model may have inferred only from the combined picture—not from any single probe.

## What it discovers

- **`api_reference.md`** (or equivalent): structured narrative documentation of the DLL’s surface area.
- **Cross-function patterns** and inferred initialization hints extracted by MC-4 for downstream use.

## How it feeds the circular enrichment pattern

The synthesis is a **durable artifact**. Run N+1 can **compare** its `api_reference.md` to run N’s to measure **improvement** (coverage, consistency, fewer contradictions) across loops.

## Dependencies (what it needs from prior stages)

- **S-03** (and below): reconciled findings, sentinel semantics, and vocabulary.
- **S-02** indirectly: probe-backed behavior embedded in findings and logs consumed during reconciliation.

## Non-goals

- S-04 does not verify runtime behavior by itself.
- S-04 does not own schema patching.
- S-04 does not close unresolved gaps.
