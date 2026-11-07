# Campaign Output Ledger Eval 01

## Role

- `campaign-output-ledger`

## Date

- `2026-04-12`

## Evaluation Mode

- retrofit proof against the completed hard-unlock dynamic campaign

## Evidence Inspected

- CAMPAIGN.md
- ACTIVE-PROMPT.md
- 26-hard01-release-commit-transition-validity-first-failed-reproof-summary.md
- 30-hard02-stale-invalidation-materialization-and-package-reproof-summary.md
- CAMPAIGN-CLOSEOUT.md
- CAMPAIGN-LOG.md

## What Was Being Tested

- can one sidecar role preserve dynamic-campaign decision memory across prompt
  start, in-flight branch changes, and prompt close
- can it improve next-prompt readability without duplicating the full prompt
  body
- can it surface workflow and role or system signals earlier than campaign
  closeout
- can it stay distinct from run-ledger auditing and generic narration

## Useful Output

- the lifecycle-aware tranche summaries now preserve:
  - blocker-before state
  - in-flight branch-shaping findings
  - workflow friction
  - role and system candidate signals
  - final blocker-after and next-prompt decisions
- the closeout packet now states clearly that it was reconstructed after the
  fact and that the next live campaign must use the role end to end
- the role's output shape is bounded enough for the GM to integrate without
  surrendering authorship of the repo-tracked artifacts

## Strongest Miss

- this evaluation is still reconstructed from an already completed campaign, so
  it cannot prove live usefulness under time pressure or context churn

## Strongest Overclaim To Avoid

- do not treat retrofit clarity as proof that the role is already stable
  enough for unattended recurring use

## Judgment Against Criteria

- specialty fit:
  - good
- bounded usefulness:
  - good
- report quality:
  - good
- signal-to-noise:
  - acceptable, but only because the retrofit was bounded to one campaign
- distinctness from `ledger-auditor`:
  - clear
- continuation usefulness:
  - directionally strong, but not yet proven live

## Decision

- `refine`

## Why

- the role clearly improves campaign reviewability and preserves decision
  surfaces that were previously getting compressed away
- the missing proof is live continuation value during an active dynamic
  campaign, not retrofit usefulness

## Required Next Proof

- the next live dynamic campaign must dispatch `campaign-output-ledger` from
  prompt start through campaign closeout
- that campaign must judge:
  - whether next-prompt clarity improved while the work was still live
  - whether workflow friction and candidate-role or candidate-system signals
    were captured early enough to matter
  - whether the role stayed non-blocking
  - whether the GM had to correct repeated noise

## Lifecycle State Recommendation

- keep `campaign-output-ledger` as `calibrating`
- promote only after one live dynamic campaign proves real continuation value
