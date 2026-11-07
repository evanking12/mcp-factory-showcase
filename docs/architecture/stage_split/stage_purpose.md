# Target Stage Purpose Surface

> Migration-only doctrine surface.
> This file describes the 11-stage target architecture, not the current live
> implementation. Current implementation truth lives in
> `api/pipeline/core/handoff_contract.py`.

This is the target one-screen purpose surface for the 11-stage architecture.
Each stage must keep one dominant assignment, one primary artifact, one local
failure boundary, and one next diagnostic step.

## Required Handoff Interpretation

For this file, a valid stage definition is not complete with purpose alone.

Every target stage should be interpretable with:

- one dominant purpose
- one primary artifact
- one advance or success condition
- one local failure boundary
- whether uncertainty is legal to carry forward
- one next diagnostic step if the stage cannot hand off yet

If a target stage cannot be read that way, it is still too blended or too
underspecified for clean migration.

Every target stage should also eventually be interpretable by its handoff
packet shape, legal coordination outcomes, and admission organization, not only
by purpose and artifact.

See
[stage_handoff_packets.md](stage_handoff_packets.md)
for the governing packet shape and reviewer/coordinator doctrine.

## N-00 setup

- purpose
  - establish run-local setup truth and initial contract baseline
- primary artifact
  - baseline schema and stage checks snapshot
- local failure boundary
  - setup contract or bootstrap failure
- next diagnostic step
  - verify startup, schema snapshot, and lane preconditions

## N-01 observational_intake

- purpose
  - gather cheap behavior and intake observations before deeper semantic work
- primary artifact
  - observational intake snapshot
- local failure boundary
  - intake missing or obviously noisy
- next diagnostic step
  - inspect intake completeness and reject obvious noise

## N-02 unlock

- purpose
  - establish any required unlock or write-mode preconditions
- primary artifact
  - unlock and pre-probe scaffolding packet
- local failure boundary
  - unlock sequence missing, invalid, or contradictory
- next diagnostic step
  - inspect unlock truth before any bounded local probe

## N-03 surface_inventory

- purpose
  - enumerate callable surfaces and cluster likely work units
- primary artifact
  - surface inventory packet
- local failure boundary
  - surface list incomplete or unstable
- next diagnostic step
  - verify callable enumeration and surface ownership

## N-04 frontier_ranking

- purpose
  - choose the cheapest high-value next slice
- primary artifact
  - priority ranking packet
- local failure boundary
  - bad frontier choice or ambiguous ranking
- next diagnostic step
  - review ranking inputs and deferment candidates

## N-05 deferment

- purpose
  - explicitly mark what should not be activated yet
- primary artifact
  - deferment decision packet
- local failure boundary
  - over-admission or under-deferment
- next diagnostic step
  - inspect deferred surfaces and admission reason

## N-06 bounded_local_probe

- purpose
  - execute the chosen frontier locally with bounded probe budget
- primary artifact
  - bounded probe log and local findings
- local failure boundary
  - local probe did not answer the chosen question
- next diagnostic step
  - inspect probe log, stop reasons, and local evidence

## N-07 local_reconcile

- purpose
  - make the local findings internally consistent
- primary artifact
  - reconciled local findings packet
- local failure boundary
  - contradiction remains inside the local slice
- next diagnostic step
  - inspect contradiction source and upstream dependency assumptions

## N-08 local_synthesis

- purpose
  - produce the local story and handoff from the reconciled findings
- primary artifact
  - local synthesis packet
- local failure boundary
  - local story is incomplete or unsupported
- next diagnostic step
  - inspect synthesis coverage and unsupported claims

## N-09 verification_and_expansion

- purpose
  - verify local truth and decide whether to broaden
- primary artifact
  - verification and expansion decision packet
- local failure boundary
  - local truth unverified or expansion decision unsupported
- next diagnostic step
  - inspect verification evidence, expansion gate, and residual ambiguity

## N-10 authority_and_finalize

- purpose
  - close the semantic chain and emit the final authority-bearing packet
- primary artifact
  - final authority and finalize packet
- local failure boundary
  - chain cannot close honestly
- next diagnostic step
  - inspect final authority inputs, closure gate, and unresolved residuals
