# Campaign Reviewer Eval 01

## Role

- `campaign-reviewer`

## Date

- `2026-04-13`

## Evaluation Mode

- retrofit proof against the live `hard01_hard02_trust_repair_v2` campaign

## Evidence Inspected

- CAMPAIGN.md
- ACTIVE-PROMPT.md
- 13-diagnose-settlement-receipt-truth-selection-family-blocker.md
- PROMPT-REVIEW-13-diagnose-settlement-receipt-truth-selection-family-blocker.md
- MORNING-PRINCIPLES-REVIEW.md
- CAMPAIGN-REVIEW-SUMMARY.md

## What Was Being Tested

- whether one reviewer can own prompt-close review, morning principles review,
  and campaign review summary without taking over branch choice
- whether the role improves observability of trusted versus untrusted state
- whether the role stays distinct from `campaign-output-ledger`

## Useful Output

- the prompt-close review makes Prompt 13's real repair versus non-authoritative
  proving result legible without rereading the full prompt
- the morning review compresses the night into one architect-facing packet with
  the 12 principles made explicit
- the campaign review summary gives the live campaign one additive review layer
  that the GM can consult without mutating canonical prompt surfaces

## Strongest Miss

- this first proof is retrofit-only and covers one completed prompt rather than
  repeated live prompt-close use across multiple checkpoints

## Strongest Overclaim To Avoid

- do not treat one useful retrofit review packet as proof that the role should
  narrate every trivial tranche

## Judgment Against Criteria

- specialty fit:
  - good
- bounded usefulness:
  - good
- report quality:
  - good
- signal-to-noise:
  - acceptable
- distinctness from `campaign-output-ledger`:
  - clear
- distinctness from `proving-authority-reviewer`:
  - clear

## Decision

- `refine`

## Why

- the role cleanly owns the observability layer that was previously falling
  back to the GM
- it sharpens operator reviewability without taking over campaign authority
- the missing proof is repeated live use at prompt close and overnight close

## Required Next Proof

- dispatch `campaign-reviewer` on live non-trivial prompt closes in the next
  active tranche sequence
- judge whether the prompt-close review remains useful without turning into
  ceremony
- judge whether the morning review meaningfully reduces prompt archaeology for
  the operator

## Lifecycle State Recommendation

- add `campaign-reviewer` as `calibrating`
- promote only after one more live campaign proves sustained value at prompt
  close and morning close
