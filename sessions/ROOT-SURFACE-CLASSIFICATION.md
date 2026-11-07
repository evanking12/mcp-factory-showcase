# Sessions Root Surface Classification

This file classifies the current top-level `sessions/` surface so later cleanup
can move files intentionally instead of by guesswork.

This is a clarification artifact only. It does not move or delete anything.

## Reading Order

If you are trying to understand current run history, start with:

- `sessions/README.md`
- `sessions/codex-runs/`
- `sessions/harness-runs/`
- `sessions/campaigns/`
- `sessions/ledger/`
- `sessions/reports/`

## Classification Buckets

### Durable review homes

These are primary human-review or durable run-history surfaces:

- `README.md`
- `codex-runs/`
- `harness-runs/`
- `campaigns/`
- `campaign-captures/`
- `ledger/`
- `reports/`
- `design_suite/`
- `engine_scaling/`
- `runtime-inputs/`
- `architecture/`
- `baseline/`
- `baseline_*`
- `nightly/`

### Historical or archival run families

These are still useful, but they are not the preferred first review surface:

- `contoso_cs/`
- `matrix/`
- `misc/`
- dated one-off run folders such as:
  - `2026-03-*`
  - `2026-04-*`
- `manual-*`
- `model-cmp-*`
- `_archive/`
- `_runs/`
- `_smoke-codex-rollout/`
- `_e2e_verify_feature/`
- `offline-e2e-*`

### Operational logs and operational trace files

These reflect runtime or service activity rather than the primary run-review
surface:

- `logs/`
- `api-start.err.log`
- `api-start.log`
- `bridge-start.err.log`
- `bridge-start.log`
- `bridge-execute-breadcrumbs.jsonl`

### Helper scripts and local analysis helpers

These are execution or inspection helpers and should not compete with run
history at the root:

- `scripts/`
- `ci-run.ps1`
- `compare.ps1`
- `run-tests.ps1`
- `score-session.ps1`
- `restart_dashboard_lab.ps1`
- `restart_local_services.ps1`
- `_analyze_findings.py`
- `_analyze_transitions.py`

### Human summaries and control artifacts

These are durable enough to keep for now, but they are summary/control outputs
rather than the core run-history surface:

- `current-gaps.md`
- `DASHBOARD.md`
- `index.json`
- `coordinator-cycle-*.md`
- `coordinator-final-report.md`
- `coordinator-state.json`
- `morning-report-2026-03-22.md`
- `overnight-2026-03-23-summary.md`
- `model-comparison-log.txt`
- `latest-floor-config-job.json`

### Root transient-candidate or relocation-candidate files

These should not stay as permanent first-class root surfaces long-term:

- `tmp/`
- `circular-test-results.json`
- `_e2e_contoso_findings_raw.json`
- `model-cmp-*.zip`
- build-style binary outputs currently at root:
  - `contoso_cs_head.dll`
  - `contoso_payments.exp`
  - `contoso_payments.lib`
  - `contoso_payments_upload.dll`
  - `contoso_payments_upload.exp`
  - `contoso_payments_upload.lib`

## First-Wave Move Targets For Later Tranches

Do not move these in this tranche. These are only the clearest next candidates:

- move top-level `*.log` files into `sessions/logs/` once that surface has its
  own README/index
- move root helper scripts and `_analyze_*.py` into `sessions/scripts/`
- move ad hoc JSON outputs into a dated review or archive home
- decide whether root binary outputs belong in a dedicated artifact/archive
  home instead of the root

## Must Not Be Touched Yet

Do not move, delete, or rewrite these in this tranche:

- `sessions/ledger/run_ledger.jsonl`
- `sessions/campaigns/`
- `sessions/design_suite/`
- `sessions/engine_scaling/`
- `sessions/harness-runs/`
- `sessions/codex-runs/`
- `bridge-execute-breadcrumbs.jsonl`

Those are high-value evidence or operational surfaces and need a more explicit
follow-up move plan if they are ever re-homed.
