# Why The Pipeline Should Split From 7 Stages To 11

> Migration-only doctrine surface.
> This file argues for the target 11-stage architecture. It is not the current
> implementation contract.

## Summary

The current 7-stage pipeline is too compressed in the middle. If we apply the
stage law strictly, each stage should fit on one screen with:

- purpose
- expected artifact
- success condition
- failure boundary
- local vs inherited
- next diagnostic step

When that law is applied to the current pipeline, the middle band does not
hold. `s02` through `s06` are not single train cars. They are bundles of
multiple assignments, multiple handoffs, and multiple failure surfaces.

That is why the current workflow too often degrades into:

- the pipeline broke
- the middle went bad somewhere
- later stages tried to rescue it
- diagnosis became archaeology instead of contract checking

The 11-stage interpretation is stronger because it separates jobs that are
related but not identical, and gives each one a clearer artifact, handoff, and
failure boundary.

## Why 7 Is Too Compressed

The front of the pipeline is still relatively bounded:

- `s00_setup`
- `s01_unlock`

The problem is the middle:

- `s02_probe` blends discovery and deep probing
- `s03_reconcile` blends local cleanup and contradiction/prerequisite shaping
- `s04_synthesis` blends local story-building and broader forward-shaping
- `s05_enrichment` blends verification and evidence backfill
- `s06_gaps` becomes a rescue zone for weaknesses that should have been caught
  earlier

This means the worst overlap sits in `s02` through `s06`.

That overlap makes it hard to answer cleanly:

- what this stage was supposed to do
- what artifact it was supposed to emit
- what failed
- whether the failure was local or inherited
- what the next diagnostic step should be

If a stage cannot answer those in one screen, it is too overloaded.

## Why 11 Is Stronger Than 9

A 9-stage architecture is a transitional compromise. It still leaves some
responsibilities blended together, especially:

- `frontier ranking + deferment`
- `verification + carry-forward or expansion decision`

Those are adjacent, but they are not the same job.

The 11-stage architecture is stronger because it separates:

- `ranking`
  - what should matter first
- `deferment`
  - what should explicitly not run yet
- `local reconcile`
  - make the local findings consistent
- `local synthesis`
  - produce the local story and handoff
- `verification`
  - decide whether the local result is trustworthy
- `expansion decision`
  - decide what broadens next

That creates cleaner train cars with less overlap and better observability.

## The 11-Stage Train-Car Shape

1. `setup`
2. `observational intake`
3. `unlock`
4. `surface inventory`
5. `frontier ranking`
6. `deferment`
7. `bounded local probe`
8. `local reconcile`
9. `local synthesis`
10. `verification / expansion decision`
11. `authority / finalize`

This is stronger than the 7-stage shape because each stage is closer to:

- one dominant assignment
- one primary artifact
- one primary failure boundary
- one main handoff

## Why This Helps

Splitting from 7 to 11 should improve:

- failure attribution
- observability
- handoff review
- checkpointing
- restartability
- easiest-first organization
- seeded findings carried into later work

It should reduce:

- stage overlap
- rescue behavior in late stages
- blurred middle-pipeline diagnosis
- expensive "give me two days and I will figure it out" failures

## Practical Interpretation

The point is not stage-count maximalism.

The point is:

- if a stage has more than one major job, split it
- if a stage has more than one primary failure boundary, split it
- if a later stage keeps rescuing it, split or redesign the earlier one

So the argument for 11 is not aesthetic. It is operational:

- 7 is too compressed to be cleanly diagnosable
- 9 is better but still compromises on overlap
- 11 is the stronger architectural target for a non-overlapping,
  assembly-line-shaped pipeline

## Handoff Sufficiency Is Part Of The Split

Stage splitting is not only about cleaner purpose and artifact boundaries.
It is also about whether each stage can honestly decide if it has done enough
to let the next stage proceed.

A stage is still overloaded if it cannot cleanly say:

- what it was supposed to do
- what it produced
- whether that output is enough to hand off
- whether the failure is local or inherited
- what the next diagnostic step should be

The 11-stage target is stronger partly because it makes those handoff
sufficiency checks easier to state and easier to review.

Later-stage rescue behavior is often evidence that an earlier stage did not
have an explicit stay or fail gate.

If a stage keeps handing off weak output and a later stage keeps compensating
for it, that is not merely bad luck in the later stage.
It is evidence that the earlier stage still lacks a real contract.
