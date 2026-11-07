# S-03 — Reconcile

## Purpose

S-03 is **truth reconciliation**. The LLM may label a function as an error even when the probe log shows success (e.g. return code 0). S-03 deterministically scans the probe log and **repairs** these mismatches. **MC-3** then classifies write-function failures: uniform sentinels (likely an **init / unlock** problem) versus mixed sentinels (likely **per-function** behavior). If MC-3 recovers an unlock sequence, the pipeline can **immediately re-probe** failed writes.

## What it discovers

- **Reconciled findings**: LLM narratives aligned with executable evidence in the logs.
- **Failure taxonomy for writes**: global init issue vs. localized API issues.
- **Optional unlock breakthroughs** surfaced by MC-3 that trigger targeted re-probing.

## How it feeds the circular enrichment pattern

Reconciled output is **ground truth** for synthesis and later stages: run N+1 inherits corrected labels and classifications, so documentation and verification are not built on contradictions.

## Dependencies (what it needs from prior stages)

- **S-02**: probe logs and raw LLM findings.
- **S-00–S-01**: sentinels, vocabulary, and unlock context to interpret return codes consistently.

## Non-goals

- S-03 does not perform broad probing.
- S-03 does not author final API documentation.
- S-03 does not turn unsupported inference into runtime truth.
