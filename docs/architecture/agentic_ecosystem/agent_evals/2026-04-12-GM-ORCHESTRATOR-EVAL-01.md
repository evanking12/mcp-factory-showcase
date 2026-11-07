# GM Orchestrator Eval 01

## Role

- `gm_orchestrator`

## Date

- `2026-04-12`

## Evaluation Mode

- retrofit proof against the live `hard01_hard02_baseline_trust_repair`
  campaign

## Evidence Inspected

- CAMPAIGN.md
- ACTIVE-PROMPT.md
- 04-hard01-baseline-rerun-summary.md
- CAMPAIGN-LOG.md
- ARCHITECT-BRIEF.md
- CAMPAIGN-CLOSEOUT.md

## What Was Being Tested

- whether the GM kept one dominant blocker at a time
- whether blocker reranking stayed evidence-led
- whether the GM preserved campaign scope and gates
- whether context pressure and writeback timing were handled honestly
- whether specialist usage improved branch choice rather than adding ceremony

## What The GM Got Right

- preserved the hard-family goal and did not broaden into unrelated cleanup
- reranked the dominant blocker from attestation to late branch-truth
  authority after the `hard-01` rerun
- preserved:
  - `branch_trust_observer`
  - local API-lane auto-resolution
  - narrow repair boundary
- kept `hard-02` closed after the red `hard-01` rerun instead of spending
  breadth budget prematurely
- used specialists on real decision-bearing seams rather than ornamental
  analysis

## Strongest Miss

- live writeback quality was directionally good but not yet mechanical
- the branch-shaping facts themselves were preserved, but workflow-health
  interpretation still depended too much on thread-local memory before the
  live writeback checkpoint was hardened

## Strongest Overclaim To Avoid

- do not treat correct blocker reranking as proof that workflow control was
  already strong enough under context pressure

## Workflow Quality Scores

- `gm_control_quality`
  - score: `2`
  - evidence:
    - blocker reranking stayed honest
    - `hard-02` was not reopened
    - scope stayed narrow
  - strongest_risk:
    - the workflow rubric was not yet mandatory while these tranches ran
  - next_correction:
    - require authoritative GM scoring at every prompt close
- `context_pressure_result`
  - score: `1`
  - evidence:
    - no known branch-shaping fact was lost
    - but some workflow interpretation lived first in chat and only later in
      durable synthesis
  - strongest_risk:
    - future campaigns could continue while workflow truth is still implicit
  - next_correction:
    - require context-pressure scoring and live writeback before continuation
- `delegation_effectiveness`
  - score: `3`
  - evidence:
    - `system-contract-tracer` localized the live owner seam
    - `ledger-auditor` correctly blocked compare-plus-triage on trust grounds
    - `campaign-output-ledger` improved compact reviewability
  - strongest_risk:
    - delegation quality was useful, but not yet being scored explicitly
  - next_correction:
    - preserve delegation scoring in tranche artifacts and closeout
- `operator_reviewability`
  - score: `2`
  - evidence:
    - the campaign left:
      - active prompt pointer
      - log
      - tranche summaries
      - closeout
      - architect brief
    - but the workflow-quality readout itself was still implicit
  - strongest_risk:
    - an architect could understand campaign state, but not GM quality or
      context-pressure quality from repo surfaces alone
  - next_correction:
    - add explicit workflow-quality blocks to the campaign system

## Decision

- `refine`

## Why

- the GM role is directionally strong and should remain parent-thread-only
- the missing piece was explicit workflow-quality instrumentation, not a change
  in GM ownership

## Lifecycle State Recommendation

- keep `gm_orchestrator` as `provisional`
- continue to treat it as `parent_thread_only`
- require repeated per-tranche workflow scoring before claiming stronger GM
  workflow discipline
