# S-00 — Setup

## Purpose

S-00 is the **foundation** of the DLL reverse-engineering pipeline. It calibrates sentinel error codes (calling functions with null arguments so the LLM can name the return codes), seeds vocabulary from user hints and binary strings, and runs static analysis on the uploaded DLL. Everything it produces becomes shared context for every later stage.

## What it discovers

- **Sentinel table**: return codes and their meanings from calibration probes.
- **Vocabulary**: terms and labels seeded from hints and strings extracted from the binary.
- **Static analysis**: structural signals from the DLL binary that constrain and inform downstream reasoning.

## How it feeds the circular enrichment pattern

If a prior run exists (`prior_job_id`), S-00 **inherits** that run’s sentinel table and vocabulary and **refines** them instead of starting cold. This is where “getting smarter over time” begins: each loop tightens the shared lexicon and error semantics before any function-level work.

## Dependencies (what it needs from prior stages)

- **Cold start**: the uploaded DLL, optional user hints, and toolchain access for static analysis.
- **Warm start**: artifacts from the previous job (sentinel table, vocab, and any inherited calibration context) when re-running with `prior_job_id`.

## Non-goals

- S-00 does not prove semantic runtime behavior.
- S-00 does not own write-unlock decisions.
- S-00 does not own broad cross-DLL organization.
