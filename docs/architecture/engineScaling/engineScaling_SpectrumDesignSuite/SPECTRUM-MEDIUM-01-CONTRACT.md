# Spectrum Medium-01 Contract

## Case Name

`medium-01` = `reservation_fanout_lineage`

## Role In The Ladder

This is the first decision-bearing case.

It exists to prove:

- one product-relevant blocker family under moderate pressure
- one meaningful bounded unlock surface
- one first decomposition decision that can still be reviewed honestly

## Transaction Story

The operator stages a release and emits:

- an operator token
- a reservation handle

That reservation handle is reused by two downstream consumers:

- `dispatch_preview.prepare_release_preview`
- `fee_quote.stage_release_fee_quote`

A late validation surface checks whether the reused handle remained trustworthy:

- `settlement_reconcile.verify_reserved_release`

## Primary Blocker Family

`lineage_materialization`

Why this blocker matters:

- it is the first product-relevant case where a runtime artifact exists but can
  fail to survive cleanly into multiple consumers

## First Intended Short-Goal Unlock Surface

Bounded unlock target:

- one or both direct fanout consumers should become partially unlockable:
  - `dispatch_preview.prepare_release_preview`
  - `fee_quote.stage_release_fee_quote`

This is strong enough to steer from while still staying medium.

## Decomposition Pressure

The first meaningful split decision is whether to:

- keep the reservation producer and first validating consumer in one reasoning
  unit
- or split by shallow module ownership

The wrong split risks making one consumer look green while the shared handle
lineage is still broken.

## Readable Diagnostics

The case should show:

- where the reservation handle is produced
- where it is reused
- where it stops being trustworthy
- whether the failure is local to one consumer or shared across both

## False Progress Definition

False progress here means:

- one consumer turns green after decomposition
- but the late validation surface still shows that the shared handle lineage
  was never preserved honestly

## Next-System Implication If This Case Fails

If `medium-01` stays noisy or misleading, the next product system to consider
is:

- stronger artifact materialization and lineage-carryover evidence between the
  producer and first fanout consumers

## Product Lesson / Next System Implication

If `medium-01` works:

- the product has a credible first proof that bounded unlock progress can
  coexist with honest blocker localization

If `medium-01` fails:

- the product likely needs stronger lineage-materialization evidence or
  consumer reuse diagnostics before it can claim product-scale robustness

## Evaluation

### What This Prompt Proved

- the first medium case now has one explicit blocker family, one bounded unlock
  surface, and one honest decomposition pressure point

### What Remains Unproven

- whether the same blocker family survives a structural change in `medium-02`

### What Changed In The Spectrum Design

- medium now has a true first proving case rather than a generic "harder than
  easy" placeholder

### Is The Planned Next Prompt Still Correct

- yes

### If Not, Write The Replacement Next Prompt Now

- not needed
