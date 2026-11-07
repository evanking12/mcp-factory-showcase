# S-07 — Finalize

## Purpose

S-07 **closes** the pipeline. **Harmonization** applies a final deterministic pass, upgrading error findings when probe-log evidence shows success. The LLM emits a **typed Python behavioral specification** and a **one-sentence DLL description**. The **AC-4 closure gate** decides whether the run is **done** or **awaiting clarification** (open questions for the user).

## What it discovers

- **Harmonization report**: deterministic alignment between labels and logs.
- **Behavioral spec**: executable-flavored summary of intended API behavior.
- **Closure state**: shipped vs. blocked-on-user-input.

## How it feeds the circular enrichment pattern

The **final vocabulary**, **behavioral spec**, and **harmonization report** become **starting knowledge** for run N+1 when the user re-runs with refinements—so the next loop begins from a documented, gated baseline instead of from scratch.

## Dependencies (what it needs from prior stages)

- **S-06**: gap outcomes and last-chance classifications.
- **S-05**: verified vs. inferred distinction.
- **S-04**: synthesis for narrative closure.
- **S-03–S-00**: reconciled findings, probes, unlock state, sentinels, and vocabulary.

## Non-goals

- S-07 does not create new runtime evidence.
- S-07 does not erase remaining clarification needs.
- S-07 does not make incomplete coverage equivalent to complete proof.
