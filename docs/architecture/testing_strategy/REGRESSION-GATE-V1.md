# Regression Gate V1

This is the first local-first regression gate for MCP Factory.

It exists to answer one bounded question:

- did the managed local lane, `easy01`, or full-chain `medium01` regress
  relative to pinned baseline roots

## Gate Surfaces

- `lane trust`
  - contract-based bounded trust check
  - not a promoted-run baseline comparison
- `easy01`
  - compared against one explicit pinned baseline output root
  - active Gate V1 path uses the Easy01 product runner and requires
    product-green summary/report fields
- `medium01`
  - compared against one explicit pinned baseline output root

## Canonical Command

```powershell
python scripts/regression/run_regression_gate_v1.py --config configs/regression/gate_v1.json
```

Default output root:

- `sessions/regression_gate/<timestamp>/`

## Verdicts

- `pass`
  - all required surfaces passed cleanly
- `pass_with_accepted_difference`
  - no regressions, but one explicitly accepted difference fired
- `fail`
  - lane trust failed
  - a required run artifact was missing
  - a suite runner failed to produce a comparable candidate root
  - or the baseline comparison detected regression

## Pinned Baseline Policy

- lane trust uses the canonical runtime contract and proving-lane validator
- `easy01` uses one explicit pinned baseline registry entry
- `medium01` uses one explicit pinned baseline registry entry
- `configs/regression/baseline_registry.json` is the canonical pinned-baseline
  registry
- Gate v1 does not auto-discover latest passing runs
- Gate v1 does not implement baseline promotion; promotion is a separate
  campaign decision that updates the pinned registry and gate config

## Current Easy01 Baseline

`easy01_product_green_baseline_promotion_v2` promoted Easy01 to the defended
product-green baseline.

- active pinned root:
  `configs/regression/pinned_baselines/spectrum_transaction_release_settlement_suite/easy-01/20260423-151031`
- active runner id: `easy01_product`
- summary case id: `easy-01-product-route`
- required Easy01 fields include `green_contract_level=product_green`,
  `product_green_eligible=true`, `route_authority_present=true`,
  `safe_to_compare=true`, `semantic_proof_satisfied=true`,
  `authoritative_proving=true`, and `blocking_signal=""`

The previous Easy01 root `20260410-082334` remains tracked as historical
compatibility evidence, not the active defended baseline.

## GitHub Actions Enforcement

The required Easy01 CI check must run Gate V1 over `lane_trust,easy-01`, not
the historical Easy01 compatibility runner. Per-target Easy01 checkpoint jobs
are diagnostics only and must use the Easy01 product runner if they are run.

Required branch protection check name:

- `Required Regression Gates / Easy01 Product Gate`

## Required Output Artifacts

- `gate-summary.json`
- `gate-verdict.json`
- `lane-trust-result.json`
- `easy01-result.json`
- `medium01-result.json`

Each result artifact must name:

- baseline root used
- candidate root used
- per-surface verdict
- reasons for failure when red

## Claim Ceiling

Gate v1 proves:

- the repo now has one local command that checks lane trust, runs the bounded
  suites, compares them to pinned baselines, and emits one final verdict

Gate v1 does not prove:

- GitHub enforcement
- baseline promotion
- full ladder governance beyond the configured surfaces
- nightly regression breadth
- `medium02` or hard-family non-regression
- a repo-wide generalized compare system for every proving family
