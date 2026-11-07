# Campaign Workflow Auditor Role Contract

## Lifecycle Status

- `merged`
- merged_into:
  - `campaign-reviewer`

## Merge Reason

The original `campaign-workflow-auditor` boundary was real enough to prove
that dynamic campaigns needed workflow pressure testing, but it is no longer
the clearest repo-facing owner for campaign workflow review.

The stronger V1 taskforce split is now:

- `campaign-reviewer`
  - prompt-close review
  - workflow review
  - morning principles review
  - campaign review summary
- `proving-authority-reviewer`
  - run-authority review after reruns and proving commands

That split reduces overlap and makes one default workflow-review owner
explicit.

## Historical Purpose

This role existed to pressure-test workflow quality for a dynamic campaign
tranche without taking over GM authority.

It previously answered:

- was the GM control quality good enough
- did context pressure threaten durable campaign truth
- did delegation improve the decision
- were the right roles considered and skipped honestly
- was the campaign still operator-reviewable without chat archaeology

## Current Do Not Use Boundary

Do not dispatch `campaign-workflow-auditor` for new work.

Use instead:

- `campaign-reviewer`
  - for prompt-close review, workflow review, campaign review summary, and
    morning principles review
- `proving-authority-reviewer`
  - for gate-bearing rerun-authority review

## Historical Record Rule

Keep this contract only as historical governance memory so older evals,
campaigns, and registry history remain interpretable after the merge.
