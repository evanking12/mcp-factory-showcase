# Proving And Regression Home

This directory is the canonical seam-level home for proving and regression
truth in MCP Factory.

Use this directory first when you need to answer:

- what the current proving families are
- which regression surfaces are active
- where baseline, compare, and promotion logic live
- which runtime proving surfaces are canonical
- which campaign-local comparison packets are subordinate rather than repo-wide
  truth

## Canonical Seams

- regression governance ladder
  - [REGRESSION-LADDER.md](REGRESSION-LADDER.md)
- regression policy and claim-ceiling law
  - [REGRESSION-POLICY.md](REGRESSION-POLICY.md)
- regression gate contract
  - [REGRESSION-GATE-V1.md](REGRESSION-GATE-V1.md)
- regression gate CI wrapper
  - [REGRESSION-GATE-CI-V1.md](REGRESSION-GATE-CI-V1.md)
- suite strategy and proving-family map
  - [SUITE-FAMILY-ROADMAP.md](SUITE-FAMILY-ROADMAP.md)
- stage proving map and breakpoint-suite routing
  - [STAGE-PROVING-MAP.md](STAGE-PROVING-MAP.md)
- efficiency activation suite design
  - [EFFICIENCY-ACTIVATION-DESIGN-SUITE-V1.md](EFFICIENCY-ACTIVATION-DESIGN-SUITE-V1.md)
  - [EFFICIENCY-ACTIVATION-DESIGN-SUITE-V1-COMPILED.md](EFFICIENCY-ACTIVATION-DESIGN-SUITE-V1-COMPILED.md)
- stage-split migration comparison suite
  - [STAGE-SPLIT-MIGRATION-COMPARISON-SUITE-V1.md](STAGE-SPLIT-MIGRATION-COMPARISON-SUITE-V1.md)
- compiled-suite green contract
  - [COMPILED-SUITE-GREEN-CONTRACT.md](COMPILED-SUITE-GREEN-CONTRACT.md)
- `S-00 -> S-01` handoff seam regression checklist
  - [S00-S01-HANDOFF-REGRESSION-CHECKLIST.md](S00-S01-HANDOFF-REGRESSION-CHECKLIST.md)

## Subordinate Surfaces

These are active surfaces, but they are indexed from this home rather than
treated as separate first-read homes.

- executable regression inventory
  - [tests/README.md](../../../tests/README.md)
- compare-run runbook and implementation
  - codex/tasks/compare-runs.md
  - codex/scripts/compare_runs.py
- promotion and compare-role governance
  - .agents/skills/baseline-promoter/SKILL.md
  - .agents/skills/regression-governor/SKILL.md
  - .codex/agents/ledger-compare-run-auditor.toml
  - .codex/agents/proving-authority-reviewer.toml
- baseline registry and gate configs
  - [configs/regression/baseline_registry.json](../../../configs/regression/baseline_registry.json)
  - [configs/regression/gate_v1.json](../../../configs/regression/gate_v1.json)
  - [configs/regression/product_proving_posture.json](../../../configs/regression/product_proving_posture.json)
- bounded local lane proof
  - [runtime/runners/proving-lane-canary/README.md](../../../runtime/runners/proving-lane-canary/README.md)
  - [docs/architecture/runtime/LOCAL-RUNTIME-OWNERSHIP-REGISTRY.md](../runtime/LOCAL-RUNTIME-OWNERSHIP-REGISTRY.md)
- campaign-local proving packets
  - `dynamic_campaigns/*/outputs/evaluations/comparison/`
  - these are canonical inside the owning campaign only

## Baseline Taxonomy

Do not use `baseline` as one undifferentiated concept.

- `promoted baseline`
  - repo-wide or family-wide comparison target that may gate regression claims
- `migration baseline snapshot`
  - bounded pre-change leg for a migration comparison such as stage-split work
- `KPI baseline`
  - numeric reporting or nightly-groundtruth comparison reference
- `package-overlap or cohesion baseline`
  - package-family or comparable-overlap reference used for attribution and
    overlap-safe claims

If a doc or artifact says only `baseline`, it should be clarified to one of the
forms above.

## Green Contract

Do not use `green` as one undifferentiated concept for compiled suites.
`COMPILED-SUITE-GREEN-CONTRACT.md` defines `compatibility_green`,
`measurement_green`, `route_green`, `semantic_green`, and `product_green`.
Historical Medium01 green is compatibility/regression green unless it proves
Ghidra-backed route authority. Compiled enterprise product-green requires the
no-source route through Ghidra-backed discovery and decision-bearing product
evidence.

## Current Rules

- This directory is the seam-level home for proving and regression truth.
- Mutable current truth is contract-backed:
  - active defended baselines live in `configs/regression/baseline_registry.json`
  - product gate membership and product-green required fields live in
    `configs/regression/gate_v1.json`
  - local proving anchor, active pressure target, active blocker signal, and
    required external check name live in
    `configs/regression/product_proving_posture.json`
- `REGRESSION-LADDER.md` defines the additive ladder and cadence classes.
- `REGRESSION-POLICY.md` defines verdict, claim-ceiling, and gating law.
- `tests/` is the executable inventory, not the seam-level doctrine home.
- `configs/regression/` is the canonical baseline and gate-policy config home.
- compare tooling, promotion tools, and campaign-local packets are subordinate
  surfaces.
- Empty placeholders that look canonical should be deleted rather than left to
  mislead readers or agents.
