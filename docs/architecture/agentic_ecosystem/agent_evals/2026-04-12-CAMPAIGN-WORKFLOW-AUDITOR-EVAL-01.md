# Campaign Workflow Auditor Eval 01

## Role

- `campaign-workflow-auditor`

## Date

- `2026-04-12`

## Evaluation Mode

- retrofit proof against the live `hard01_hard02_baseline_trust_repair`
  campaign

## Evidence Inspected

- CAMPAIGN.md
- ACTIVE-PROMPT.md
- 05-diagnose-hard01-late-branch-truth-authority.md
- CAMPAIGN-LOG.md
- ARCHITECT-BRIEF.md
- CAMPAIGN-CLOSEOUT.md

## What Was Being Tested

- whether a bounded close-phase role can pressure-test campaign workflow
  quality without taking over branch choice
- whether the role can score:
  - GM control
  - context pressure
  - delegation effectiveness
  - operator reviewability
- whether it stays distinct from `campaign-output-ledger`

## Useful Output

- the role cleanly exposes that the campaign was product-directionally strong
  while still workflow-weaker than it looked
- it catches the already-known writeback-timing weakness as a workflow issue,
  not just a general “docs later” complaint
- it reinforces that delegation was useful enough to keep, rather than
  flattening all specialists into one generic good-or-bad verdict

## Strongest Miss

- this first proof is retrofit-only, so it cannot yet prove that the role
  improves workflow behavior live under prompt-close time pressure

## Strongest Overclaim To Avoid

- do not treat one successful retrofit scoring pass as proof that this role
  should fire on every tiny campaign checkpoint

## Workflow Quality Pressure Test

- `gm_control_quality`
  - score: `2`
  - evidence:
    - blocker reranking was honest and scope stayed bounded
  - strongest_risk:
    - workflow scoring was not yet mandatory while the tranche ran
  - next_correction:
    - keep GM scoring mandatory and use this role only as a pressure test
- `context_pressure_result`
  - score: `1`
  - evidence:
    - no major branch-shaping fact appears lost
    - but workflow-quality interpretation depended partly on later synthesis
  - strongest_risk:
    - context pressure could still hide future workflow regressions if nobody
      scores them explicitly
  - next_correction:
    - dispatch this role on milestone or suspicious prompt closes
- `delegation_effectiveness`
  - score: `3`
  - evidence:
    - `ledger-auditor` and `system-contract-tracer` clearly changed the next
      move
  - strongest_risk:
    - delegation quality could still be under-recorded without the new rubric
  - next_correction:
    - keep delegation scoring in tranche summaries and architect briefs
- `operator_reviewability`
  - score: `2`
  - evidence:
    - compact campaign surfaces existed and were readable
    - workflow-health interpretation was not yet explicit
  - strongest_risk:
    - operator reviewability could look better than it really is unless the
      workflow rubric is durable
  - next_correction:
    - require the rubric in log, summaries, brief, and closeout

## Distinctness Check

- distinct from `campaign-output-ledger`:
  - yes
- why:
  - `campaign-output-ledger` preserves live deltas
  - `campaign-workflow-auditor` pressure-tests the quality of the resulting
    workflow behavior

## Decision

- `keep and refine`

## Why

- the role answers a distinct recurring question
- the role has a stable bounded output
- the role should remain non-authoritative and calibrating until live prompt
  closes prove that it adds signal without noise

## Lifecycle State Recommendation

- add `campaign-workflow-auditor` as `calibrating`
- dispatch it only on milestone or suspicious tranches until at least one live
  end-to-end dynamic campaign proves sustained value
