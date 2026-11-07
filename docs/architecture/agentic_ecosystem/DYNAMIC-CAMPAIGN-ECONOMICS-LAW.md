# Dynamic Campaign Economics Law

## Purpose

This doctrine defines how governed dynamic campaigns should preserve speed
without sacrificing trust, reviewability, or blocker honesty.

It exists because the repo already has strong laws for:

- trust
- reviewability
- specialist-role governance
- durable writeback

but still needs one reusable law for campaign economics:

- when to stop spending end-to-end proving budget
- when to drop to a cheaper trusted loop
- when a hard-family rerun is justified
- how to show later whether the time spent was worth it

This doctrine is the reusable control surface for that.

## Core Thesis

Hard-family campaigns are too slow when one expensive run is forced to do all
of these at once:

- diagnose lane trust
- localize the blocker
- validate the code change
- prove the hard-family outcome

That is not one loop.

The correct governed shape is three loops under a strict lane-trust gate:

1. `lane_trust_loop`
2. `lowest_level_blocker_loop`
3. `authoritative_proving_loop`

Hard-family work belongs only in loop 3.

## Strict Lane-Trust Gate

Default trust policy is strict-gate.

If lane trust is not green, do not spend expensive hard-family proving budget
unless a narrower trusted route-around is explicit and documented.

`lane_trust_loop` owns:

- identity
- readiness
- canary
- failure-domain classification

It does not own:

- hard-family semantic diagnosis
- blocker reranking from suite results

## Tranche Classes

Every executed dynamic tranche must declare exactly one `tranche_class`.

Canonical values:

- `lane_trust`
- `blocker_localization`
- `bounded_fix`
- `authoritative_proving`
- `closeout`

These tranche classes are not cosmetic labels.

They determine:

- what loop the tranche is in
- what validation surfaces are legal
- what roles are the default fits
- whether hard-family spend is allowed

## Loop Law

### `lane_trust_loop`

Use this loop when:

- lane trust is unknown
- lane trust is yellow or red
- a proving surface may be stale, miswired, or incompatible
- a canary or readiness packet is the active gate

Allowed work:

- identity checks
- readiness checks
- canary runs
- compatibility checks
- failure-domain work

Disallowed work:

- hard-family proving
- semantic blocker reranking from suite results

### `lowest_level_blocker_loop`

Use this loop when:

- lane trust is green enough
- the current blocker seam is not yet reduced to the smallest trustworthy
  boundary
- a local or system-shaped seam still needs a cheaper reproducer

Allowed work:

- blocker localization
- smallest reproducer creation
- bounded instrumentation
- bounded code changes in the owning layer
- validation below hard-family level first

Disallowed work:

- repeated end-to-end reruns as the primary localization method

### `authoritative_proving_loop`

Use this loop only when:

- lane trust is green enough
- the blocker seam has already been reduced
- a bounded fix or route-around has already been validated on the cheapest
  trusted surface available

Allowed work:

- exactly one decision-bearing proving action
- proving-authority review
- blocker reranking from that reviewed evidence

Disallowed work:

- spending multiple end-to-end reruns to discover basic trust or localization
  facts that should have been resolved in earlier loops

## Rerun Gate Law

Do not launch an expensive hard-family rerun unless all five rerun gates pass.

Required gates:

- `checkpoint_first_gate`
  - what checkpoint or target-local proof was used first, or why no trustworthy
    seam-local proof exists
- `evidence_gate`
  - what new evidence will this rerun produce
- `control_gate`
  - what hidden variable is better controlled now
- `decision_gate`
  - what concrete decision will the rerun allow afterward
- `trust_gate`
  - what authoritative truth surface makes this rerun legal to trust
- `scope_gate`
  - why this rerun is still the smallest trustworthy boundary

This doctrine reuses the rerun-gate reasoning from `roadblock-handler`.

It does not replace it with a second competing standard.

Required writeback shape whenever an expensive rerun is proposed:

- each gate must record exactly one of:
  - `pass`
  - `fail`
  - `blocked`
- use `n/a` only when the tranche is not proposing an expensive rerun at all
- do not collapse the five gates into one prose-only summary
- `checkpoint_first_gate=fail` blocks the expensive rerun unless the operator
  explicitly asks for confirmation, promotion, or baseline evidence

## Architecture Ceiling Gate

Dynamic campaigns must not keep running local-fix tranches after the current
architecture shape has become the blocker.

The ceiling trigger is mandatory when either condition holds:

- the same proving ceiling or same dominant blocker family survives `3`
  consecutive executed tranches
- or `2` or more of these signals are true in the latest tranche evaluation:
  - later stages are rescuing earlier-stage weakness
  - reruns add evidence but do not raise the claim ceiling
  - the missing thing is clearly a system, contract, or stage shape rather than
    another local fix
  - bounded improvements are occurring inside the wrong container and not
    changing the branch ceiling

If the ceiling trigger fires:

- hard-family spend is blocked
- another local-fix tranche is blocked
- the GM must write one explicit `architecture_ceiling_check` before
  continuation

The `architecture_ceiling_check` must decide exactly one next allowed action:

- `continue_local_fix`
- `split_stage_or_contract`
- `build_missing_system`
- `change_proving_frontier`
- `stop_and_reframe`

This is a gate, not a new loop, tranche class, or role.

## One Expensive Loop, One Job

Every expensive rerun must declare exactly one primary job.

Required fields:

- `single_primary_job_of_this_rerun`
- `why_this_rerun_is_not_being_used_for_a_second_stronger_job`

Allowed primary jobs:

- `lane_revalidation`
- `blocker_localization_confirmation`
- `bounded_fix_validation`
- `authoritative_proving_decision`

Unexpected extra truths discovered by the rerun count as spillover evidence,
not proof that the rerun was well-scoped.

## Default Dispatch Matrix

Use the current role roster more intentionally.

Do not create new roles for this doctrine by default.

### `lane_trust`

Default:

- `campaign-output-ledger`

Fitting additions:

- `system-contract-tracer`
  - only when the tranche is tracing the proving-lane trust system
- `verification_gate_bot`
  - for lane-sensitive checks and evidence sufficiency
- `roadblock-handler`
  - immediately if trust is yellow or red, or if two focused investigations
    fail to improve
- `proving-authority-reviewer`
  - only after a canary or proving command returns

### `blocker_localization`

Default:

- `campaign-output-ledger`

Fitting additions:

- `roadblock-handler`
  - primary narrowing tool
- `system-contract-tracer`
  - only when the blocker is clearly system-shaped

### `bounded_fix`

Default:

- `campaign-output-ledger`

Fitting additions:

- `verification_gate_bot`
  - for check sufficiency
- `code_review_bot`
  - for code-bearing trust or boundary changes

### `authoritative_proving`

Default:

- `campaign-output-ledger`

Fitting additions:

- `proving-authority-reviewer`
  - mandatory after every rerun or proving command
- `triage-next-step`
  - only when compare-run output actually exists
- `run_auditor`
  - only when run trust is the active gate
- `ledger_compare_run_auditor`
  - only when compare attribution is the active gate

### `closeout`

Default:

- `campaign-output-ledger`

Fitting additions:

- `campaign-reviewer`

## Roadblock Mode Law

Roadblock mode is the speed-preserving fallback, not an exception.

Enter roadblock mode immediately when:

- lane trust is red
- lane trust is yellow and the strict gate lacks an approved route-around
- two focused investigations fail to improve
- repeated runs add no new evidence
- contradiction appears between trust surfaces

Choose exactly one route:

- `fix`
- `defer`
- `escalate`
- `route_around`

Do not keep feature or proving pressure on top of a red trust layer.

## Family-Blocker Escalation Law

If the same blocker family survives two bounded cycles:

- update `FAMILY-BLOCKER-SYSTEM-WRITEBACK`
- classify whether it is still a `family_blocker` or has become a
  `missing_system`
- do this before another expensive hard-family rerun

This is the main anti-regression rule for campaign speed.

It prevents repeated suite spending on the same unresolved seam.

## Standard Operating Sequence

Every future governed campaign should follow this order:

1. open tranche summary and ledger at prompt start
2. classify the tranche as one of the five tranche classes
3. state the dominant blocker and cheapest trusted validation surface
4. run the role scan from the default dispatch matrix
5. execute only the matching loop
6. if the tranche is `bounded_fix`, validate below hard-family level first
7. if the tranche is `authoritative_proving`, run one proving action only
8. require proving-authority review before blocker rerank
9. if evidence is weak or trust breaks, switch to roadblock mode instead of
   rerunning
10. write campaign-economics delta and blocker movement before continuation

## Required Reviewability Fields

Every tranche summary must also record:

- `tranche_class`
- `cheapest_trusted_validation_surface`
- `single_primary_job_of_this_rerun`
- `why_this_rerun_is_not_being_used_for_a_second_stronger_job`
- `rerun_gate_result`
- `why_this_is_not_a_harder_loop`
- `failure_domain_if_red`
- `campaign_economics_delta`

Required `campaign_economics_delta` fields:

- `end_to_end_runs_started`
- `authoritative_runs_gained`
- `local_validations_run`
- `blocker_narrowing_delta`
- `time_spent_without_new_evidence`
- `was_hard_family_budget_spent`
- `was_that_spend_justified`

If a tranche spends hard-family budget without a strong `rerun_gate_result`,
the tranche must self-classify as workflow failure and trigger roadblock mode.

If a tranche spends hard-family budget without one explicit
`single_primary_job_of_this_rerun`, the tranche must also self-classify as
workflow failure and trigger roadblock mode.

## Required Closeout Readout

Every campaign closeout must also answer:

- whether the campaign obeyed the three-loop law
- whether any hard-family spend was used to debug lane trust
- whether blocker localization happened below suite level before reruns
- which role dispatches actually reduced iteration cost

## Non-Goals

Do not:

- broaden `triage-next-step` into a generic campaign router
- promote new specialist roles during this doctrine pass unless a real missing
  seam emerges
- let `campaign-output-ledger` replace GM judgment
- treat this doctrine as permission for higher throughput at lower proof
  quality

The goal is faster trustworthy iteration, not maximum throughput at the cost
of proof quality.
