# Campaign Workflow Auditor Merge 01

## Role

- `campaign-workflow-auditor`

## Date

- `2026-04-13`

## Decision

- `merge`

## Merged Into

- `campaign-reviewer`

## Why

- the repo now needs one clear default owner for prompt-close workflow review,
  campaign review summary, and morning principles review
- keeping both `campaign-workflow-auditor` and `campaign-reviewer` as active
  workflow reviewers would create overlapping triggers and ambiguous ownership
- `proving-authority-reviewer` now owns the gate-bearing rerun-authority slice
  that should never have been bundled into a generic workflow reviewer

## What Should Be Preserved

- the original insight that dynamic campaigns need explicit workflow-pressure
  testing
- the boundary that workflow review must stay read-only and non-authoritative

## What Is Retired

- using `campaign-workflow-auditor` as the default active workflow reviewer for
  new campaign work

## Current Rule

- keep the historical contract, manifest, and prior eval so older campaign
  artifacts remain interpretable
- do not dispatch this role for new work while the merge stands
