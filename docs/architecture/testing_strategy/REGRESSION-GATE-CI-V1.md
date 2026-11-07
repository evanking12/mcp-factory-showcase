# Regression Gate CI V2

## Purpose

This document defines the current ladder-shaped GitHub Actions wrapper around
the local-first regression system.

CI is hybrid:

- hosted fast checks on every `push` and `pull_request`
- Windows self-hosted regression workflows for relevant `push` and
  `pull_request` changes
- `workflow_dispatch` fallback for manual runs while the self-hosted runner is
  unavailable or not yet trusted for automatic use

## Workflows

- `.github/workflows/fast-checks.yml`
  - hosted universal checks
- `.github/workflows/required-regression-gates.yml`
  - ladder-shaped required merge path
  - current required status surfaces:
    - `Easy01 Product Gate`
- `.github/workflows/easy01-diagnostic-checkpoints.yml`
  - non-required Easy01 checkpoint diagnostics
  - runs after required regression gate failure or manual dispatch
  - uses the Easy01 product runner for per-target artifacts
- `.github/workflows/medium01-checkpoints.yml`
  - auto-run non-blocking Tier 3 evidence workflow
  - current status surfaces:
    - `Medium01 Lane Precheck`
    - `Medium01 Checkpoints`

## Self-Hosted Runner Contract

The self-hosted runner must provide:

- Windows
- repo checkout access
- Python 3.10-compatible environment
- ability to install repo dependencies
- ability to run PowerShell startup and lane validation
- ability to host the managed local API lane on a dedicated CI port
- ability to host the managed local bridge lane on a dedicated CI port
- required secrets:
  - `OPENAI_API_KEY`
  - `GUI_BRIDGE_SECRET`
  - `PIPELINE_API_KEY` when local API auth still requires it
- no Azure dependency
- no cloud runtime dependency

## Automatic vs Manual Mode

The regression-bearing workflows are controlled by one repo variable:

- `ENABLE_REGRESSION_GATE_AUTO`

Behavior:

- if `ENABLE_REGRESSION_GATE_AUTO=true`
  - relevant `push` and `pull_request` changes trigger the regression-bearing
    workflows automatically
- otherwise
  - the same workflows remain available through `workflow_dispatch`
  - hosted fast checks still run automatically

This lets CI start in practical manual mode without redesigning the workflows.

## Proof Routing

Changed files are classified by proof risk before expensive regression work is
chosen. The operator-facing policy lives in:

- `docs/architecture/testing_strategy/PROOF-ROUTING-AND-HARD01-FOCUS.md`

Current rule of thumb:

- red changes require full product-baseline authority in CI or promotion
- yellow changes use Medium02 or the touched suite locally by default
- grey changes use fast checks and change-admission checks
- green changes use static checks unless review finds hidden runtime coupling

## Dedicated CI Lane

The self-hosted workflows intentionally do not share the developer's default
local lane.

Current dedicated CI defaults:

- API: `18201`
- bridge: `18090`

The runtime contract remains canonical at `8201` and `8090` for normal local
operator use, but the startup and runtime helpers now allow explicit
environment-based port overrides so the self-hosted runner can execute the
heavy gate without colliding with live development work on the same machine.

## Canonical Gate Command

CI must call the same command used locally, while selecting the smallest
relevant surface:

```powershell
python scripts/regression/run_regression_gate_v1.py --config configs/regression/gate_v1.json
```

Current surface selection examples:

- required easy01 product gate:
  - `--surfaces lane_trust,easy-01 --fail-fast`
- medium01:
  - `--surfaces medium-01 --fail-fast`

Current ladder-aligned merge law:

- `Fast Checks`
  - always required
- `Easy01 Product Gate`
  - required for current regression-bearing changes
  - includes lane trust plus Easy01 product baseline comparison
- `Easy01 Diagnostic Checkpoints`
  - non-required diagnostics only
  - preserve per-target checkpoint artifacts when the product gate fails
- `Medium01 Checkpoints`
  - auto-run and visible, but not required for merge yet

`medium01` remains one ladder member.
Its checkpoint-bearing sub-verdicts are operator-facing diagnostic surfaces,
not new top-level tiers.

Branch protection should require `Required Regression Gates / Easy01 Product
Gate`. It should not require Easy01 diagnostic checkpoint job names.
