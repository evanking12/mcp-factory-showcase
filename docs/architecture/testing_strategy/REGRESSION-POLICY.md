# Regression Policy

## Purpose

This document defines how regression posture affects claims, commits, pushes,
campaigns, and future CI in MCP Factory.

Canonical operator surfaces:

- gate command:
  - `python scripts/regression/run_regression_gate_v1.py --config configs/regression/gate_v1.json`
- baseline registry:
  - `configs/regression/baseline_registry.json`
- ladder definition:
  - `docs/architecture/testing_strategy/REGRESSION-LADDER.md`

## Verdict Classes

- `green`
  - required gate passed cleanly
- `red`
  - required gate ran and found a regression or failed to produce a comparable
    packet
- `fail_closed`
  - the gate itself is authoritative and localized the failure, but the
    protected surface is not green
- `unproven`
  - the required gate has not yet been run or no trustworthy comparison exists

## Claim Ceiling Law

- `green`
  - strong non-regression claim is allowed for the covered surface only
- `red`
  - implementation or investigation progress may be claimed, but not protected
    surface health
- `fail_closed`
  - bounded progress may be claimed only as:
    - gate exists
    - failure is localized
    - healthier claim remains unproven
- `unproven`
  - only implementation-progress claims are allowed

Do not treat implementation completion as proof that the product remained
healthy.

## Baseline Comparison Law

- when a pinned baseline exists, strong claims require comparison against it
- baseline truth lives in `configs/regression/`, not in `sessions/`
- `sessions/regression_gate/` is evidence output only
- lane trust is contract-based and does not use promoted-run baseline
  comparison

## Minimum Tier Expectations

- Tier 0 only may be enough for:
  - bounded logic or schema changes with no runtime, runner, stage, or proving
    effect
- Tier 1 is additionally required for:
  - lane, startup, readiness, bridge, or harness trust changes
- Tier 2 and above are required when:
  - the change can affect compiled-suite proving behavior
  - a branch wants to claim preserved compiled-ingest behavior
  - a campaign is steering from suite-level evidence

Use the cheapest trustworthy tier that actually covers the claim.

## Stage Migration Blast Radius

Stage migration work must map the touched surface to the stage trace markers
before claiming non-regression.

| Marker | Meaning | Minimum local gate | Claim ceiling |
| --- | --- | --- | --- |
| `red / owned` | Stage-owned implementation changed. | Stage-local tests plus artifact and contract tests for that stage. | Local stage contract only unless a higher tier runs. |
| `yellow / dependency` | Shared dependency changed. | Tests for every stage that lists the dependency in `TRACE.md`. | Shared dependency contract only unless affected compiled behavior is re-proven. |
| `gray / upstream` | Intake, discovery, worker, or feeder changed. | Upstream tests plus the first affected stage seam. | Feeder/seam health only unless lane or compiled-suite tiers run. |
| `green / output` | Emitted artifact shape or path changed. | Producer, packaging, snapshot, and downstream consumer tests. | Artifact compatibility only unless runtime behavior is re-proven. |

If a change can affect compiled-suite proving behavior, Tier 2 or higher is
required before claiming compiled-ingest non-regression. If a change touches
runtime lane, bridge, startup, or harness trust, Tier 1 is also required before
claiming the lane is trustworthy.

The red/yellow/gray/green marker chooses blast radius. The regression ladder
chooses how high the claim may go.

## Campaign And Commit Law

Runtime- or pipeline-affecting campaigns must record:

- `regression_posture`
- `regression_result`

Non-trivial commits must separate:

- implementation changed
- regression posture changed or did not change

## Future CI Law

Future GitHub Actions must consume this policy rather than inventing a
parallel regression model.

CI is a ladder, not one flat pass/fail surface.

| CI layer | Purpose | Runs when | Claim ceiling |
| --- | --- | --- | --- |
| Fast Checks | Cheap syntax, unit, contract, docs/governance, schema, packet, route-snapshot, and change-admission checks. | Every push and pull request. | Tier 0 contract/governance/artifact compatibility only. |
| Path-aware checks | Run the exact relevant cheap checks from changed paths and `check_registry.json`. | Every push and pull request once the runner exists. | The affected system contract only. |
| Runtime smoke / lane trust | Prove the managed lane can start and is trustworthy enough for suite work. | Runtime, lane, bridge, harness, or startup changes; manual dispatch when needed. | Tier 1 lane trust only. |
| Baseline comparison suites | Compare current behavior to pinned baselines. | Migration, proving, and runtime behavior changes when strong non-regression is claimed. | Baseline-relative claim for the covered suite only. |
| Nightly / full regression | Broader confidence and artifact preservation. | Nightly, scheduled, release-oriented, or manually dispatched. | Broad confidence only for covered tiers. |
| Failure artifact upload | Preserve diagnosis packets and logs. | Every failing CI layer. | Explains failure class; does not raise the proof tier by itself. |

Cheap checks should be plentiful.
Expensive checks should be claim-driven.

Fast Checks should include stable lane-independent scripts and tests whenever
they can fail with useful local diagnosis. They must not include live DLL jobs,
bridge execution, self-hosted lane startup, or compiled-suite proving.

Path-aware checks are now an executable Tier 0 selection layer:

- command:
  - `python scripts/regression/run_path_aware_checks.py --paths-file changed-files.txt --output-root .tmp/path-aware-checks --mode ci --execute`
- source of truth:
  - changed paths
  - `configs/regression/check_registry.json`
  - `configs/regression/observability_promotion_triggers.json`
- output:
  - changed systems
  - selected blocking checks
  - skipped nonblocking or manual checks
  - execution results
  - claim ceiling
  - observability promotion triggers

The path-aware runner is the first place Codex should inspect when deciding
which cheap checks explain a change. It does not prove lane trust, compiled
suite behavior, or broad product non-regression. Fast Checks keeps the broad
static pytest list until the path-aware runner has enough hosted evidence to
become the primary cheap selector.

Expected failures are acceptable only when they are explicitly classified.
Unexplained red CI is not useful product signal.

## Live Checkpoint Observability

Long-running checkpoint jobs must explain themselves while running.

If a hosted or local checkpoint step spends minutes inside a silent `Run
checkpoint` command, the regression system is not observable enough for the
current migration frontier.

Every compiled checkpoint runner should emit and preserve live observations
with:

- job id
- phase
- stage
- status message
- progress
- elapsed time
- status-stability age
- signature-stability age
- internal stage span and span-stability age when available
- soft-stall hint when visible
- claim ceiling

Live observations are diagnostic evidence. They do not prove semantic
correctness or compiled-suite non-regression by themselves.

Use in-process stage spans before splitting the compiled checkpoint workflow
into separate per-stage GitHub Actions jobs. Per-stage workflow checkpoints are
a future expansion for when span-level observability is still insufficient or
checkpoint/resume plus artifact handoff is reliable enough to avoid adding
false CI noise.

When a checkpoint times out, the summary packet should show the last live
observation and the suspected stall class. If that evidence is missing, classify
the result under `lane_runtime_reliability_classification` before widening any
stage migration.

The current required merge path is:

- `Fast Checks`
- `Easy01 Product Gate`
  - runs Gate V1 over `lane_trust,easy-01`
  - enforces the promoted Easy01 product-green baseline

`Easy01 Diagnostic Checkpoints` and `Medium01 Checkpoints` are visible
diagnostic/evidence workflows rather than required merge checks.

Heavier tiers may run on different cadence without displacing cheaper lower
tiers.
