# Spectrum First Rollout Contract

## Summary

The first Spectrum Design Suite rollout should turn the current design note
into a bounded, decision-complete proving family contract.

This suite is not meant to replace Contoso as the live product lane. It is
meant to become the next architecture benchmark family after Northstar and
Atlas.

The first rollout should stay small and intentional:

- `easy-01`
- `medium-01`
- `medium-02`
- `hard-01`

The suite should be one transactional family, not four unrelated tests.

## Why This System Exists

The repo now has:

- Contoso as the live product-facing lane
- Northstar as the semantic transfer proving family
- Atlas as the first harder successor-suite transfer proof

What it still lacks is a proving family that tests difficulty itself as a
first-class dimension.

The Spectrum Design Suite exists to answer:

- whether blocker families remain stable as difficulty rises
- whether the pipeline can reproduce the same blocker doctrine across multiple
  controlled cases
- where interwoven pressure becomes architecture-breaking
- whether hard cases still produce useful diagnostics even when unlock counts
  lag

## What This Does Not Replace

This system does not replace:

- Contoso live-lane repair and package-floor work
- Northstar or Atlas as prior proving families
- compare or promotion policy work
- the current live Contoso prompt chain

It adds:

- a difficulty-graded proving family
- a benchmark surface for invalidating current blocker assumptions
- a structured ladder for easy -> medium -> hard architecture stress

## Why Now, Not Later

Now is the right time because:

- the design-suite campaign seam is no longer the main unknown
- the repo has enough design-suite infrastructure to support a richer proving
  family
- the current risk is validating blocker doctrine too narrowly on Contoso and
  too cleanly on Northstar/Atlas

The Spectrum Design Suite should become the place where blocker doctrine is
stress-tested instead of merely reused.

## Transactional Family Narrative

The first spectrum family should use one shared transactional narrative across
all four cases.

That family should preserve these invariants:

- staged transaction flow
- one or more runtime artifacts that must survive across steps
- confirmation or downstream consequence instead of purely local truth
- enough shared structure that blocker families can be compared across bands

This narrative should let the ladder grow by pressure, not by changing domains.

## Shared Blocker Taxonomy

The first rollout should reuse a small explicit blocker taxonomy across the
family.

The intended starting taxonomy is:

- `setup_gate`
  - broad initialization or prerequisite state is missing
- `lineage_materialization`
  - a runtime artifact exists transiently but is not preserved cleanly enough
    for downstream use
- `shared_state_reuse`
  - one producer output is reused by multiple consumers with different needs
    and one or more consumers fail
- `interwoven_lineage_ambiguity`
  - multiple plausible paths or branches exist and only one is trustworthy

Taxonomy rules:

- `easy-01` should use exactly one blocker family at a time
- both medium cases must reuse at least one blocker family intentionally
- `hard-01` must introduce `interwoven_lineage_ambiguity`
- hard may also reuse medium blocker families, but only after adding a new
  pressure class

## First Rollout Contract

### easy-01

Purpose:

- prove basic coherence on a dominant staged chain

Required characteristics:

- one dominant dependency chain
- low ambiguity
- one blocker family at a time
- highly authored expected outputs

Success criteria:

- expected vs observed is easy to read
- blocker classification is obvious and stable
- the case is green or near-green quickly

### medium-01

Purpose:

- prove the first reusable blocker family under moderate transactional pressure

Required characteristics:

- one producer feeding multiple consumers
- shared state reused differently
- one repeated blocker family

Success criteria:

- the pipeline gets meaningful partial or stronger coverage
- the blocker sits in an explainable place
- the case is decision-bearing, not just noisy

### medium-02

Purpose:

- reproduce the same blocker family class in a different transactional shape

Required characteristics:

- same blocker family class as `medium-01`
- different structural layout
- still human-reviewable expected vs observed

Success criteria:

- the blocker family repeats honestly
- the pipeline can explain why it is the same family instead of merely similar
- this case confirms or falsifies reproducibility

### hard-01

Purpose:

- introduce genuinely hard interwoven lineage pressure without requiring early
  campaign success

Required characteristics:

- ambiguous lineage
- multiple plausible paths with one trustworthy path
- replay instability or state decay
- partial observability

Success criteria for v1:

- the pipeline narrows honestly
- ambiguity stays visible
- diagnostics are high-value
- blocker-family splits or observer gaps become clearer

Hard explicitly does not require in v1:

- campaign-shaped proof
- real campaign admission
- high unlock counts

## Band Promotion Rules

The ladder should promote cautiously.

Easy is considered ready when:

- it is coherent
- readable
- and green enough to stop being a design question

Medium is considered convincing only if:

- at least one medium case is green enough to steer from
- the second medium case confirms or falsifies blocker reproducibility
- expected vs observed remains human-readable in both

Hard is considered successful in v1 if:

- it is locally diagnosable
- it preserves ambiguity honestly
- it reveals missing systems or blocker splits

Hard should remain local-only until:

- medium is convincing
- the taxonomy remains readable
- and the suite family is reviewable as one ladder

## Explicit Non-Goals For V1

Do not require v1 to:

- solve hard
- run hard as a real campaign
- broaden compare or promotion
- add a second spectrum family
- maximize unlock count over diagnostic value

## Retire / Supersede Surface Check

This rollout should supersede only one missing surface:

- the lack of a difficulty-graded proving family

It should not retire:

- current design-suite proving families
- the live Contoso lane
- current design-suite campaign-bearing infrastructure

## Expected Review Value

If the first rollout is successful, the suite should give us:

- a benchmark family stronger than a single curated suite
- a medium band that genuinely tests blocker reproducibility
- a hard band that teaches us what the pipeline still lacks

## Current Honest Next Step

The prompt-chain review and rollout design tranche is now complete.

The next honest step is:

- fixture implementation for the first spectrum family

That implementation should be driven by:

- `SPECTRUM-FAMILY-CONTRACT.md`
- `SPECTRUM-SPLIT-AND-OBSERVER-CONTRACT.md`
- the four case contracts
- `SPECTRUM-IMPLEMENTATION-READINESS.md`

The main implementation risk is now:

- authored-case sharpness
  - medium must not become too polite
  - hard must not become too vague
