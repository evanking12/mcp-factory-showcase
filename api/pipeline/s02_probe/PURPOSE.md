# S-02 — Probe

## Purpose

S-02 is the **core discovery engine**. It orders functions by uncertainty (simpler, more constrained targets first so vocabulary accumulates), then runs each through a dedicated LLM agent that can invoke the function with varied arguments. The agent sees the full invocable registry, accumulated findings, the sentinel table, and decompiled C for the current target.

S-02 exposes three runtime-visible responsibilities while preserving `s02_probe`
as the compatibility parent:

- `s02_probe_ordering`: order invocables and preserve prerequisite-state planning.
- `s02_invocation_execution`: construct arguments, execute calls, and observe raw runtime behavior.
- `s02_evidence_capture`: persist evidence, findings/checkpoints, and boundary recalibration.

## What it discovers

- **Per-function behavioral hypotheses**: arguments, return semantics, side effects, and working example calls when probes succeed.
- **Growing shared vocabulary**: each successful probe adds terms and patterns that make the next function easier to interpret.
- **Probe logs**: the raw ground truth of what was called and what the DLL returned.

## How it feeds the circular enrichment pattern

Findings from run N become **“already explored”** context for run N+1: the next loop can **skip** stable results, **refine** uncertain ones, or focus budget on failures. The vocab and findings compound across loops rather than resetting.

## Dependencies (what it needs from prior stages)

- **S-00**: sentinels, vocabulary seed, static context.
- **S-01** (when relevant): knowledge that write mode is active and any required init sequence.
- **Warm start**: prior findings and probe history so the ordering and agent context reflect what was already learned.

## Non-goals

- S-02 does not own setup/static extraction.
- S-02 does not own final reconciliation of contradictory findings.
- S-02 does not own human-readable synthesis.
- S-02 does not remove or redefine the legacy `s02_probe` compatibility parent.
