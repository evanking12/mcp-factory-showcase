# S-01 — Unlock

## Purpose

S-01 discovers how to **unlock WRITE functions**. Many DLLs require a specific initialization sequence before state-changing APIs succeed (payments, updates, persistence, etc.). S-01 uses LLM code reasoning over decompiled C to infer XOR checksums, magic values, and required call order so the rest of the pipeline can operate in **write mode** when applicable.

## What it discovers

- Candidate and validated **initialization sequences** that transition the DLL into a writable state.
- **Cryptographic or validation artifacts** implied by the decompilation (e.g. XOR checksums, magic constants).
- A durable signal for downstream stages: whether write probing is expected to work and under what preconditions.

## How it feeds the circular enrichment pattern

The **winning init sequence** is **persisted** so run N+1 can **replay** it immediately instead of rediscovering it. Each loop can also refine partial unlock hypotheses using richer global context from later stages (when the pipeline is re-entered with `prior_job_id`).

## Dependencies (what it needs from prior stages)

- **S-00**: sentinel table, seeded vocabulary, and static-analysis context.
- **Warm start**: any persisted unlock sequence or partial unlock state from a prior job.

## Non-goals

- S-01 does not own static extraction or packet production.
- S-01 does not own broad per-function probing.
- S-01 does not own final semantic documentation.
