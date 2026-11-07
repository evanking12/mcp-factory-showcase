# Sessions

This folder is the human-facing home for run history, not just a dump of machine
output.

If you are reviewing the project after a run, start here before opening raw run
folders.

This snapshot starts with an empty `index.json`. The session tools populate it
from new local runs. Raw historical runs and outreach data are kept separately.

---

## What Belongs Here

`sessions/` is for run history and review surfaces.

It should contain:

- run families
- codex run outputs
- harness runs
- campaign outputs
- reports
- ledger history
- archived historical runs

It should not be treated as the primary home for:

- disposable temporary files
- long-lived runtime caches
- generated build byproducts
- top-level scratch scripts or binaries

Those belong elsewhere.

---

## Current High-Value Homes

Use these first:

- `codex-runs/`
  - bounded Codex task outputs, summaries, artifacts, notes, and bug records
- `harness-runs/`
  - automated harness validation history
- `campaigns/`
  - campaign-scoped run groupings and outputs
- `ledger/`
  - append-only run ledger
- `reports/`
  - higher-level human-readable summaries

Useful but more machine-oriented:

- `runtime-inputs/`
  - preserved inputs used by runs

Historical or clutter-prone:

- ad hoc dated top-level run folders
- `manual-*`
- `model-cmp-*`
- `_runs/`
- `_tmp-*`
- `_smoke-*`
- other one-off experiment folders

These are still useful, but they are harder to navigate and should not be the
first place a human starts.

---

## Fastest Review Order

When you want to understand what just happened:

1. `sessions/codex-runs/<active-run-family>/.../summary.json`
2. that run family's `artifacts/WHERE-TO-LOOK.md` if present
3. key artifact or blocker notes from that run
4. `sessions/ledger/run_ledger.jsonl` for comparable run context
5. `sessions/reports/` if a higher-level summary exists

If the run was campaign-backed, also review:

1. `sessions/campaigns/`
2. the run's campaign attribution artifacts
3. the compare or blocker outputs for that campaign

---

## Relationship To Other Data Homes

- `sessions/`
  - human review and durable run history
- `local-data/`
  - active local runtime storage and machine-oriented artifacts
- `logs/`
  - operational logs and scratch captures
- `tmp/`
  - disposable temporary files

If a folder is hard to review but important to history, it should move toward
`sessions/` or gain an index here.

If a folder is machine-oriented and noisy, it should not be treated as a
primary review surface.

---

## Current Problem

`sessions/` contains useful history, but its top level mixes:

- active run families
- archived experiments
- one-off manual runs
- reports
- scripts
- scratch-like leftovers

So the folder is valuable, but harder to navigate than it should be.

Treat this README as the first review map until a fuller cleanup pass lands.
