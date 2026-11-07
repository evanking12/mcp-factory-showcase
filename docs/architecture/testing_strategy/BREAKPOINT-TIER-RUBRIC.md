# Breakpoint Tier Rubric

## Purpose

This is the canonical rubric for measuring stage, seam, coordinator, and
bottom-up breakpoint maturity.

Breakpoint suites exist to make pipeline strength observable in increments.
They must not turn into scorecard theater. A tier only matters when it is tied
to a real blocker family, a deterministic expected behavior, a named owner, and
an honest claim ceiling.

## Canonical Scorecard Shape

Every breakpoint scorecard row must follow this shape:

`stage/seam/coordinator/window -> breakpoint family -> ownership_type -> tier ladder -> current tier -> target tier -> claim ceiling`

Required fields:

| Field | Meaning |
| --- | --- |
| `stage/seam/coordinator/window` | The runtime stage, handoff seam, coordinator boundary, or bounded stage window under pressure. |
| `breakpoint family` | The independent weakness variable being tested. |
| `ownership_type` | The owner class from this rubric. |
| `tier ladder` | The Tier 0-5 path for this breakpoint family. |
| `current tier` | The highest tier backed by real evidence today. |
| `target tier` | The next useful proving target, not the final product dream. |
| `claim ceiling` | The strongest claim the current evidence legally supports. |
| `family_invariant` | The durable property the family protects, not just the observed symptom. |
| `current_evidence_tier` | The strongest proof class currently backing the row: unit/local, checkpoint/target-local, compiled suite, or repeated cross-suite. |
| `tier_lift_target` | The next invariant-strengthening move and proof surface needed to raise confidence. |
| `predicted_suite_impact` | Which suites or anchors should move, remain stable, or not need rerun if the lift works. |
| `writeback_required` | The posture, signal-map, family-map, tier-matrix, or weakness-register surfaces that must be updated after proof. |

## Baseline Classification States

Full-baseline campaigns may classify rows below the target tier without fixing
them. These are baseline states, not maturity promotions:

| State | Meaning |
| --- | --- |
| `failed_tier1` | A valid Tier 1 attempt exposed a product, stage, seam, or window weakness. |
| `blocked_at_tier1` | Tier 1 could not be measured honestly because the required harness or owner surface is missing. |
| `failed_tier2` | A valid Tier 2 attempt exposed a product, stage, seam, or window weakness. |
| `blocked_at_tier2` | Tier 2 could not be measured honestly because the required harness or owner surface is missing. |
| `deferred_as_tier3_shaped` | A Tier 2 fixture would be theater because the meaningful pressure requires ambiguity, conflict, or harder composition. |
| `not_applicable` | The row is not a real breakpoint after inspection and should be merged, removed, or replaced. |
| `planned_unimplemented` | The row depends on an unimplemented component and cannot honestly enter the Tier 1/Tier 2 ladder yet. |

## Ownership Types

| ownership_type | What it tests | Example |
| --- | --- | --- |
| `stage-owned` | One stage's own semantic obligation. | `S-00B static_evidence` extracts bounded callable inventory without claiming runtime truth. |
| `seam-owned` | Producer output plus consumer interpretation. | `S-00C -> S-01` admitted targets alter probe ordering while fallback remains intact. |
| `coordinator-owned` | A coordinator narrows, groups, defers, escalates, or arbitrates between stages. | A future post-S-00 coordinator trims a rich packet before S-01. |
| `bottom-up window` | A short chain of stages where a single-stage or seam test is insufficient. | `S-00B -> S-00C -> S-01` proves static evidence becomes usable admission. |
| `full-suite baseline` | Composition evidence across the broader pipeline. | `Easy01`, `Medium01`, hard-family, or heldout real-world suites. |

## Tier Ladder

| Tier | Expected fixture shape | Allowed claim | Cannot claim | False-progress example |
| --- | --- | --- | --- | --- |
| `Tier 0` | Contract, unit, schema, or synthetic packet support only. | The local contract logic can be checked cheaply. | Product-shaped behavior, compiled binary realism, runtime composition, or stage strength. | Synthetic packet passes and is reported as stage maturity. |
| `Tier 1` | Easy compiled breakpoint or equivalent product-shaped fixture with simple semantics and one controlled pressure variable. | The stage, seam, or coordinator survives one easy realistic pressure case. | Medium pressure, adversarial ambiguity, cross-boundary maturity, or broad non-regression. | One small DLL passes and the whole stage is called strong. |
| `Tier 2` | Medium compiled pressure with noisier names, more distractors, richer strings, or more realistic artifact breadth while remaining deterministic. | The owner handles moderate pressure for the named breakpoint family. | Hard ambiguity, cross-DLL dependencies, coordinator-needed judgment, or real-world readiness. | Tier 1 fixture is made larger without a materially new pressure variable. |
| `Tier 3` | Hard compiled pressure with static-thin surfaces, conflicting hints, partial exports, weak strings, or repeated blocker-family pressure. | The owner handles hard single-family pressure with honest deferral and stable artifacts. | Cross-boundary adversarial behavior, multi-family product confidence, or full-suite success. | A hard-sounding fixture has unclear expected behavior or no blocker ownership. |
| `Tier 4` | Cross-boundary or adversarial breakpoint: multi-DLL hints, misleading names, deferred dependencies, or coordinator-required narrowing. | The boundary handles adversarial or cross-stage/cross-DLL pressure for the named family. | Heldout real-world behavior or generalized product success. | Cross-DLL noise is added but the expected handoff decision is not deterministic. |
| `Tier 5` | Heldout real-world style, batch-derived, hard-family, nightly, or manual expensive reference. | The breakpoint family holds under realistic expensive pressure. | Universal correctness or unrelated breakpoint-family strength. | A broad suite is used to claim local stage strength without failure localization. |

Synthetic or unit-only evidence is Tier 0 only. It can support contracts and
runner logic, but it cannot promote a breakpoint to Tier 1 or higher.

## Tier Promotion Evidence

Tier promotion is evidence-sensitive:

- unit, synthetic, and local proof stays low tier and cannot claim compiled or
  product-shaped maturity;
- checkpoint or target-local proof can raise confidence only for the isolated
  seam it freezes and replays;
- compiled suite proof can raise family maturity when attribution to the
  breakpoint family is clear and the expected behavior is deterministic;
- repeated cross-suite proof is required before a family can be treated as
  highest-confidence or heldout-realistic.

A tier lift must name the family invariant being strengthened before
implementation starts. A symptom is not enough. For example, `child wait bug`
is not a family invariant; `parent/child terminalization must always produce
wait-return, returncode, output-scan, or confirmed hang authority` is.

## Stage-First Derivation

Breakpoint families must be derived stage-first:

`stage obligation -> weakness variables -> breakpoint families -> tier ladders -> claim ceiling`

Do not start from a convenient fixture and assign it to a stage afterward.

For each stage, seam, coordinator, or window, ask:

- What is this owner supposed to do?
- What systems does it use?
- What artifacts does it emit?
- What decisions does it make?
- What information can it lose, distort, overtrust, undertrust, widen, narrow, or defer incorrectly?
- What independent variables would invalidate the claim we want to make?

Those independent variables become breakpoint families. If one stage accumulates
too many unrelated families, that is a signal to consider a coordinator,
handoff seam, or further runtime split.

## Finding Routing

| Finding class | Route to |
| --- | --- |
| Producer emits malformed, missing, too-wide, or under-evidenced material. | Producer stage or producer-owned artifact contract. |
| Handoff packet is valid but harmful, ambiguous, too broad, or misprioritized. | `seam-owned` breakpoint family. |
| Consumer ignores, overtrusts, or loses fallback around producer guidance. | Consumer stage. |
| Coordinator narrows, groups, defers, or escalates incorrectly. | `coordinator-owned` breakpoint family. |
| A short chain fails only when combined but each local contract passes. | `bottom-up window`. |
| Corrective or destructive enterprise action reports success without binding the result to the exact object corrected, rejected, revoked, quarantined, rolled back, or denied. | Enterprise survivability family, hard-family signal map if observed under hard/full-suite evidence, and the producing stage family only for the local production seam it owns. |
| A broad suite fails without local attribution. | Full-suite baseline until a narrower breakpoint is created. |
| The owner cannot legally solve the issue with its current obligation. | Architecture gap and possible stage/coordinator/system redesign. |

Before implementing a breakpoint-family lift, predict suite impact: which
suites should move, which anchors should remain stable, and which suites do not
need rerun. If proof diverges from the prediction, update the scorecard or
tier-lift map instead of forcing the original story.

## Scorecard Interpretation

Use the scorecard to reason about:

- `pipeline average`: broad maturity trend across scored breakpoint families.
- `critical-path floor`: the lowest tier on a required product path.
- `weakest link`: the lowest-scoring important stage, seam, coordinator, or window.
- `coverage shape`: whether a stage has too many unrelated breakpoint families and may own too much.

Do not rely on the average alone. A high average can hide one Tier 0 critical
handoff that poisons downstream work.

## Honesty Rules

- Do not promote a tier without a materially stronger pressure variable.
- Do not count renamed or duplicated tests as new breakpoint maturity.
- Do not let synthetic packets, mocks, or Python-only helpers claim Tier 1+.
- Do not treat `Easy01`, `Medium01`, or hard-family success as local stage
  strength unless the failure and success attribution is local.
- Do not claim a stage is strong when only a seam-owned breakpoint passed.
- Do not hide known uncertainty by raising the claim ceiling.
- Do not add shallow tiers just to show progress.
- Do not lift a family tier without recording `family_invariant`,
  `current_evidence_tier`, `tier_lift_target`, `predicted_suite_impact`, and
  `writeback_required`.
- Do not treat a new signal as understood until it has an owner, evidence path,
  tier position, and next classification proof.

The useful loop is:

`split to reduce choking and expose truth -> define breakpoint families -> raise the weakest critical-path tier -> confirm with broader baselines -> repeat`

## Current Anchor Example

| Scope | ownership_type | Breakpoint family | Current tier | Target tier | Claim ceiling |
| --- | --- | --- | --- | --- | --- |
| `S-00C -> S-01` | `seam-owned` | `admission pressure` | `Tier 1` | `Tier 3` | `handoff survives one easy compiled pressure case` |

This does not prove that all of S-00 is strong. It proves one seam-owned
pressure family has a Tier 1 compiled anchor.
