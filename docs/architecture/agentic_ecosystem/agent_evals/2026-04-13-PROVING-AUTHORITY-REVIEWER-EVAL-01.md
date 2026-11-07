# Proving Authority Reviewer Eval 01

## Role

- `proving-authority-reviewer`

## Date

- `2026-04-13`

## Evaluation Mode

- retrofit proof against Prompt 13 rerun authority in
  `hard01_hard02_trust_repair_v2`

## Evidence Inspected

- 13-diagnose-settlement-receipt-truth-selection-family-blocker.md
- PROMPT-REVIEW-13-diagnose-settlement-receipt-truth-selection-family-blocker.md
- PROVING-AUTHORITY-hard-01-rerun-10.md
- PROVING-AUTHORITY-hard-01-rerun-11.md
- ACTIVE-PROMPT.md

## What Was Being Tested

- whether one bounded review role can decide if a rerun is authoritative enough
  to steer the next branch
- whether it cleanly distinguishes stale-lane invalidity from fresh-lane
  run-control invalidity
- whether it stays distinct from `run_auditor` and `ledger-auditor`

## Useful Output

- rerun-10 is rejected cleanly as stale-lane invalid rather than being
  misclassified as product-semantic failure
- rerun-11 is rejected for product truth while still being accepted as evidence
  that the live blocker shifted to proving-lane and run-control reliability
- the role's output makes the next-prompt legality explicit

## Strongest Miss

- this proof still covers one campaign and two closely related reruns rather
  than multiple proving families

## Strongest Overclaim To Avoid

- do not replace `run_auditor` or `ledger-auditor` entirely; this role owns
  run-authority legality, not every narrower trust or ledger question

## Judgment Against Criteria

- specialty fit:
  - strong
- bounded usefulness:
  - strong
- report quality:
  - good
- signal-to-noise:
  - good
- distinctness from `run_auditor`:
  - acceptable and worth keeping separate
- distinctness from `ledger-auditor`:
  - clear

## Decision

- `refine`

## Why

- the role answers a real recurring question that the GM must know before
  steering from proving evidence
- it is more specific than the broader run-trust roles already in the repo
- it improves legal branch choice without taking over synthesis

## Required Next Proof

- use `proving-authority-reviewer` live on the next rerun or proving command
  whose result could steer a campaign
- verify that the artifact is produced before blocker rerank and next-prompt
  choice
- confirm that it stays bounded instead of drifting into broader campaign
  review

## Lifecycle State Recommendation

- add `proving-authority-reviewer` as `calibrating`
- promote only after one more live proving-family checkpoint shows repeated
  gate-bearing value
