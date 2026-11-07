# Spectrum Medium-02 Contract

## Case Name

`medium-02` = `attestation_reuse_confirmation`

## Role In The Ladder

This is the reproducibility case.

It exists to confirm or falsify whether the same blocker doctrine from
`medium-01` still holds in a different transactional shape.

## Transaction Story

The operator stages a release and later emits an attestation packet rather than
reusing the first reservation handle directly.

That attestation packet is then reused by:

- `invoice_sync.stage_release_invoice`
- `entitlement_sync.stage_customer_entitlement_update`

A later confirmation surface decides whether the attestation packet was ever
trustworthy:

- `settlement_reconcile.confirm_attested_release`

## Structural Difference From Medium-01

`medium-01` uses immediate fanout from the reservation producer.

`medium-02` changes the shape by:

- inserting a later attestation-producing step
- moving the shared-state reuse to a downstream packet rather than the initial
  handle
- keeping the late validator but changing its position in the flow

## Same Blocker Family Claim

Primary blocker family:

- `lineage_materialization`

This counts as the same family only if:

- the packet exists transiently
- both downstream consumers depend on it
- the packet fails because trust-preserving lineage was not carried forward,
  not because an unrelated setup or ambiguity problem took over

## What Must Match Across Medium-01 And Medium-02

- the primary blocker family diagnosis
- the need for lineage to survive into downstream consumers
- a late truth surface that decides whether the shared artifact was valid

## What Should Differ Across Medium-01 And Medium-02

- the structural location of the reused artifact
- the immediate shape of the consumers
- the point where the late validator reinterprets earlier local success

## Same Family Vs Merely Similar Difficulty

Same blocker family means:

- the same underlying artifact-preservation doctrine is being tested

Merely similar difficulty means:

- the case is hard for a different reason but still feels medium-sized

If the evidence points to the latter, reproducibility failed.

## Doctrine Split If Reproducibility Fails

If `medium-02` does not support the same-family claim, the first doctrine split
to consider is:

- separate immediate fanout lineage loss
- from delayed attestation lineage loss

## Product Lesson / Next System Implication

If reproducibility holds:

- the product has evidence that one blocker doctrine is reusable across more
  than one transactional shape

If reproducibility fails:

- the product should split the doctrine before claiming medium-band generality

## Evaluation

### What This Prompt Proved

- the second medium case is now a real falsification test rather than just a
  second example

### What Remains Unproven

- whether hard can teach useful failure without dissolving into generic red

### What Changed In The Spectrum Design

- medium now has an explicit comparison surface for doctrine reuse

### Is The Planned Next Prompt Still Correct

- yes

### If Not, Write The Replacement Next Prompt Now

- not needed
