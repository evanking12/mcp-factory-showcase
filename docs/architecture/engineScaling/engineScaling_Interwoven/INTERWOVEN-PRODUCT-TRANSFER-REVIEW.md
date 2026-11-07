# Interwoven Product Transfer Review

## Summary

This is the first bounded beyond-Contoso transfer review for the interwoven
system.

The chosen harder proving family is:

- a transactional package family with staged commits, replayable state tokens,
  shared state carriers, and producer-to-several-consumer fanout

The product-facing pilot that makes this family relevant is:

- a potential mainframe COBOL transaction package pilot

This review is intentionally not an implementation plan for COBOL runtime
adoption. It is a transfer-risk review that makes the next bounded move
explicit without pretending the current Windows/DLL execution layer already
transfers.

## Chosen Proving Family

The first beyond-Contoso proving family should be:

- transactional package flows with:
  - staged initialization
  - transaction or session handles
  - replayable nonce or token state
  - shared state reused across several consumers
  - one producer feeding several downstream consumers
  - ambiguity around stale, forked, or competing upstream state

This is the right proving family because it preserves the interwoven planning
problem while reducing dependence on Contoso-specific DLL naming or business
semantics.

## Transfer Hypothesis

The transfer hypothesis is:

- the interwoven system should transfer cleanly to any transactional package
  family where the hard problem is still:
  - who produced state
  - who consumed it
  - whether the dependency is direct, shared-state mediated, or staged
  - what must stay live together
  - what can be preserved as trusted lower-floor truth

In other words:

- if the target system still has bounded producer-consumer, shared-state, and
  staged-chain relationships, then the interwoven taxonomy, artifact family,
  stress model, and runtime projection layer should transfer more cleanly than
  the current DLL-specific execution assumptions

## What Transfers Cleanly

The parts that now look generic enough to transfer are:

- interwoven taxonomy
- producer-consumer artifact shape
- shared-state artifact shape
- staged-chain artifact shape
- contradiction-visible synthetic stress
- bounded runtime projection
- session-owned canonical truth with campaign-owned summary projection
- the rule that interwoven surfaces do not replace package-floor comparison law

These are planning and evidence surfaces, not Windows-specific runtime
surfaces.

## What Remains Contoso-Shaped

The parts that remain too Contoso-shaped to treat as product-generic are:

- Win32 DLL execution assumptions
- upload and analyze-path discovery flow
- fixture naming that still looks like function-prefix families
- current session-owned hints that depend on explicit DLL names
- Contoso-specific truth manifests and canonical args
- the current assumption that one bounded runtime lane is a DLL-centric lane

These are exactly the seams that should not be overclaimed in a product-facing
pitch.

## Product Risk Boundaries

The major transfer risks are:

- assuming the current execution adapters transfer to mainframe or COBOL
- assuming current DLL/package discovery translates directly to transaction
  programs or copybook-driven interfaces
- assuming current state-token extraction and argument-shaping logic is already
  portable
- assuming current fixture success implies product readiness

The product-safe claim right now is narrower:

- the repo now has a stronger generic interwoven planning and evidence system,
  but the execution adapters and domain-specific runtime surfaces still need a
  separate transfer tranche

## What This Makes Safer

This review makes the next product decision safer because it separates:

- what already looks generic
- what is still adapter-specific
- what must be stress-proven before a real pilot claim broadens

That means a future mainframe or COBOL pilot can be framed honestly as:

- reuse the interwoven planning and evidence architecture
- add new execution and discovery adapters
- re-prove the model on one bounded transactional family

not as:

- the current DLL execution engine already works for COBOL

## Next Bounded Move

The next bounded move should be:

1. create one contract-only transactional proving family that drops DLL and
   Win32 assumptions but preserves:
   - producer-consumer edges
   - shared-state carriers
   - staged chains
   - stale or forked state
   - one producer feeding several consumers
2. keep it adapter-free at first:
   - manifest-only
   - artifact and observer proofs only
   - no live runtime claims
3. only after that, decide whether a real pilot adapter tranche is justified

This is the smallest move that tests transfer honestly without pretending the
execution layer is already portable.

## What Remains Unproven

Still unproven:

- non-DLL execution and discovery adapters
- copybook or transaction-contract parsing
- real enterprise ambiguity outside the curated fixture world
- promotion/comparison rules once interwoven evidence becomes product-facing
  in a non-Contoso domain

## Closeout

The repo now has a bounded beyond-Contoso interwoven direction:

- stronger than ambition-only planning
- narrower than a fake product rollout
- explicit about what remains Contoso-shaped

That is the correct state for the next expansion step.
