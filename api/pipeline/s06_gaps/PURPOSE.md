# S-06 — Gaps

## Purpose

S-06 is the **last chance** for functions that still fail. **Gap resolution** retries them with the richest context the pipeline has assembled: all findings, MC decisions, and verification results. **MC-6** runs **comprehensive** code reasoning on decompiled C for **every** remaining failure, with the full history of unlock attempts as extra context. This is often where **autonomous unlock discovery** succeeds because the model has maximum knowledge.

## What it discovers

- **New or refined unlock hypotheses** and retry outcomes for stubborn APIs.
- **Final classifications** for holdouts before finalize (success, clarified failure mode, or explicit unknown).

## How it feeds the circular enrichment pattern

Gap-resolution **outcomes** merge back into the **starting findings** for run N+1 when the user re-runs with `prior_job_id`, so the next loop does not repeat the same blind spots.

## Dependencies (what it needs from prior stages)

- **S-05**: verification results and enriched schema.
- **S-04**: synthesis for narrative and parameter context.
- **S-03**: reconciled truth and MC-3 classifications.
- **S-02 / S-01 / S-00**: probe history, unlock state, sentinels, and vocabulary.

## Non-goals

- S-06 does not hide unresolved uncertainty.
- S-06 does not replace verification.
- S-06 does not own final closure state.
