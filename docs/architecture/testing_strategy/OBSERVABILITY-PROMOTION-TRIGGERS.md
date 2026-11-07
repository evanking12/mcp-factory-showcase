# Observability Promotion Triggers

## Purpose

This document defines when MCP Factory should stop widening migration work and
build the next observability system instead.

The goal is not to block all migration.
The goal is to prevent the repo from relying on memory to decide when the
regression system is no longer explanatory enough.

Machine-readable trigger config:

- `configs/regression/observability_promotion_triggers.json`

Executable trigger reader:

- `scripts/regression/run_path_aware_checks.py`

## Core Law

After CI, regression, proving, or migration work, Codex must inspect the
path-aware check output before widening the migration.

The required question is:

- did one of the observability promotion triggers fire or enter watch state?

If yes, Codex must recommend the next bounded observability system before
claiming the repo is ready to widen migration.

## Trigger Families

| Trigger | Build when | Why |
| --- | --- | --- |
| `lane_runtime_reliability_classification` | A lane, runner, runtime, dependency-install, or workflow-adjacent failure cannot be distinguished from product regression. | Red CI is not useful if infrastructure failure and product failure collapse into one bucket. |
| `baseline_breakage_map_generation` | A migration tranche changes behavior, artifacts, packets, or consumers and failure ownership still requires human synthesis. | Ambitious migrations should fail into a map: what changed, what broke, who owns it, and what next. |
| `scheduled_or_manual_heavier_baselines` | Tier 0 or Tier 1 is green but the claim needs compiled-suite or baseline-relative proof. | Heavy suites should be run because the claim requires them, not because the repo lacks cheaper attribution. |

`lane_runtime_reliability_classification` also fires when a long-running
checkpoint only exposes a silent `Run checkpoint` step and does not preserve
live phase, stage, progress, status-stability age, signature-stability age, and
soft-stall evidence. A red gate without live diagnosis is not enough to widen
migration safely.

If a stage-level soft stall is visible but still too broad to name the internal
operation, the next bounded observability system should be in-process stage
span instrumentation before per-stage GitHub Actions job splitting. Workflow
stage checkpoints become appropriate after span evidence is insufficient or
checkpoint/resume is strong enough to split safely.

## Interpretation

- `not_fired`
  - no immediate observability expansion is required
- `watch`
  - the surface is adjacent to the trigger; expand only if red or claim pressure
    appears
- `fired`
  - the next bounded system should be considered before widening migration

## Current Order

1. Path-aware check runner.
2. Lane/runtime reliability classification when red CI cannot separate
   infrastructure failure from product regression.
3. Baseline-relative breakage map generation during S-00 and later migration
   when ownership attribution becomes too manual.
4. Scheduled or manual heavier baseline suites when the claim needs compiled or
   baseline-relative proof.

## What This Does Not Replace

This document does not replace:

- `REGRESSION-POLICY.md`
- `REGRESSION-LADDER.md`
- `check_registry.json`
- dynamic campaign closeout
- human product judgment about whether a claim matters

It exists to make the next observability system discoverable from repo evidence
instead of conversation memory.
