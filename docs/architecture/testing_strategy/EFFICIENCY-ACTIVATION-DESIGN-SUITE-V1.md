# Efficiency Activation Design Suite v1

## Purpose

`efficiency_activation_design_suite_v1` is a product-shaping suite, not a
speed demo.

Its purpose is to test whether the pipeline can handle a `medium-01` /
`medium-02`-level problem with a better activation policy:

- organize first
- rank first
- defer intelligently
- deepen selectively
- reuse first-pass outputs on pass two

The suite should inherit medium-band semantic pressure from Spectrum medium
rather than dropping to an easier toy case.

The benchmark question is:

- can the engine produce a trustworthy, useful first-pass operational map for
  a medium-band package, then use that map to improve the second pass without
  probing everything deeply on pass one?

This suite is specifically for:

- activation policy
- first-pass planning
- second-pass leverage
- workflow economics
- selective deepening

It is not primarily for:

- hard-family semantic proving
- proving-lane trust
- deep interwoven state reasoning
- generic runtime benchmarking

## Why This Suite Exists

The product cannot scale by treating every function and every module as
immediately worthy of deep probing.

The pipeline needs a planning-phase capability just as a human technical team
does:

- admit and organize the package
- decide what matters first
- defer the rest explicitly
- preserve enough structured context so the second pass does not restart cold

This suite therefore exists to improve workflow economics for all later work,
not just to make one benchmark finish sooner.

If this suite succeeds, later campaign families should benefit from:

- better first-pass operator usefulness
- fewer wasted end-to-end runs
- better blocker localization
- more disciplined activation
- stronger second-pass reuse

## Relationship To Spectrum Medium

This suite should be Spectrum-medium derived.

That means it should preserve the same semantic difficulty band as
`medium-01` and `medium-02` while changing the success condition.

`medium-01` and `medium-02` already establish:

- one real medium-band blocker family
- one meaningful reuse or lineage story
- one late confirmation surface that can falsify shallow progress

This suite should preserve those strengths while asking a different product
question:

- not just "can the engine solve the case?"
- but "can the engine solve the case economically and in staged passes?"

The suite should therefore remain meaningfully difficult because:

- there is real ambiguity
- there are multiple plausible frontiers
- there is enough surface area to require staging
- brute-force deep probing of everything would be obviously wasteful

## Fixture Shape

Base the fixture on the existing Spectrum medium-band transactional system and
derive a package-shaped case from that same family.

Required fixture properties:

- same semantic difficulty band as `medium-01` / `medium-02`
- enough callable surfaces to force ranking and deferral
- at least one shared artifact or lineage story so prioritization is
  meaningful
- at least one false-positive frontier where brute-force deepening would waste
  effort
- at least one deferred surface that should not be activated on pass one
- no deep cross-DLL interwoven initialization requirement as the primary
  blocker; that belongs to a later suite family

Recommended v1 shape:

- one medium-band package with `6-10` modules or DLL-equivalent surfaces
- `20-40` meaningful callable candidates total
- one medium-band reusable blocker family comparable to lineage
  materialization or delayed attestation reuse
- one late confirmation surface that makes bad first-pass prioritization
  visible

## Floors

This suite explicitly tests staged activation.

Each floor must export something the next floor is allowed to assume. This
follows the floor-to-ceiling development doctrine already used elsewhere in the
repo.

### Floor 0: Admission

This floor establishes:

- package accepted
- duplicate and noise surfaces rejected
- identity, manifest, and broad surface inventory created

This floor must export:

- admitted package identity
- rejected or noise inventory
- module or surface manifest

The next floor is allowed to assume only that the package shape is known, not
that semantic importance is known.

### Floor 1: Inventory And Ranking

This floor establishes:

- callable surfaces inventoried
- likely producer or consumer clusters identified
- likely high-value or high-risk frontier ranked
- obviously deferrable surfaces marked

This floor must export:

- callable inventory
- frontier ranking
- deferred-surface list
- first-pass operator-useful map

The next floor is allowed to assume only that the first frontier is justified
enough to deepen, not that deferred surfaces are solved.

### Floor 2: Selective Deepening

This floor establishes:

- only the chosen frontier is deeply analyzed
- medium-band semantic work starts here
- late truth surfaces remain visible but are not all activated immediately

This floor must export:

- deepened frontier report
- pass-one trust packet
- unresolved-but-deferred surface list

The next floor is allowed to assume that pass one produced bounded,
machine-readable reusable outputs, not that the whole package was solved.

### Floor 3: Second-Pass Reuse

This floor establishes:

- pass two consumes first-pass outputs instead of restarting cold
- only newly justified surfaces become active
- the system either improves the result or honestly shows where first-pass
  planning was weak

This floor must export:

- pass-two activation delta
- reuse report
- pass-two outcome report
- economic comparison packet

## Required Outputs

The suite should require machine-readable outputs for both passes.

### First-pass outputs

- `package_inventory`
  - admitted modules or surfaces
  - rejected or noise items
- `activation_plan`
  - active floor
  - chosen frontier
  - deferred surfaces
  - rationale for deferment
- `priority_ranking`
  - top candidate surfaces or clusters
  - confidence
  - expected upside
- `operator_useful_map`
  - compact operational picture of what matters now
- `pass_one_trust_packet`
  - enough authority to justify second-pass reuse of pass-one outputs

### Second-pass outputs

- `pass_two_activation_delta`
  - what became newly active and why
- `pass_two_reuse_report`
  - what pass-one outputs were consumed
  - what was reused unchanged
  - what was invalidated
- `pass_two_outcome_report`
  - whether selective deepening improved the result
  - whether the first-pass ranking was directionally correct

### Economic outputs

- `time_to_useful_map`
- `surfaces_deeply_probed_pass_one`
- `surfaces_deeply_probed_pass_two`
- `deferred_surface_count`
- `reuse_success_rate`
- `wasted_deep_probe_count`

## Acceptance Criteria

The suite passes only if all of these are true:

- first pass produces a useful map before full deep probing of the entire
  package
- first pass activates only a bounded subset of the total meaningful surfaces
- deferred surfaces are explicit, not merely omitted
- the chosen frontier is justified and reviewable
- second pass consumes first-pass outputs explicitly rather than restarting
  cold
- second pass either:
  - improves the result with bounded additional activation
  - or honestly shows that pass-one planning was weak and where it was weak
- late truth surfaces remain capable of falsifying bad prioritization
- the suite leaves enough evidence to compare selective deepening versus
  brute-force everything as a workflow shape, even if brute-force is not the
  main path

Strong v1 pass signal:

- the engine reaches a comparable medium-band semantic outcome with better
  staging, better reuse, and a more useful first-pass operator output than a
  flat deep-probe strategy

## Pass-two Reuse Rules

Pass two may consume from pass one only these categories:

- admitted package inventory
- ranked candidate frontier
- producer or consumer grouping hypotheses
- trustworthy artifact lineage clues
- explicitly preserved deferrals
- compact operator-useful map
- pass-one trust packet

Pass two may not blindly trust:

- weak semantic conclusions from non-authoritative pass-one surfaces
- unresolved contradictions
- deep claims about deferred surfaces
- fixture-specific shortcuts inferred from prompt memory alone

If a pass-one output is reused, pass two must record:

- what was reused
- why it was trusted enough
- what new evidence justified deeper activation

## Required Pre-Pipeline Systems

Before the main semantic pipeline begins, this suite assumes a distinct
pre-pipeline organization layer exists and should be tested.

Required systems:

- `package_admission_system`
  - broad intake, dedupe, noise rejection, identity
- `surface_inventory_system`
  - callable inventory and module or surface map
- `frontier_ranking_system`
  - choose the likely high-value or high-risk next slice
- `defer_policy_system`
  - explicit not-yet-active surfaces
- `pass_reuse_policy`
  - what pass two is allowed to inherit

These systems are product-critical because they decide:

- what becomes active first
- what stays frozen
- what gets postponed
- how the workflow gets faster over time instead of paying full rediscovery
  cost forever

## GPT-4o And Future Model Routing

Model routing should not be part of v1 pass or fail.

The v1 suite should first prove the workflow shape itself:

- planning and intake
- ranking
- selective deepening
- second-pass reuse

Future model-routing evaluation can then reuse the same suite and fixture.

Likely future placement:

- planning, intake, and ranking
  - cheaper or faster model candidate such as `gpt-4o`
- deep semantic inference
  - stronger model tier
- verification and authority
  - smaller validation-oriented or deterministic layer where possible

Follow-up evaluation track:

- same suite
- same fixture
- same outputs
- compare one-model workflow versus tiered-model workflow
- judge whether `gpt-4o`-quality planning preserves ranking quality and
  improves economics

For v1, the suite only needs to leave enough stage boundaries and artifacts to
support that later comparison.

## Test Cases And Scenarios

- `bounded_first_pass`
  - first pass admits the package, inventories the surface, ranks a frontier,
    and defers the rest
- `late_truth_falsifies_bad_frontier`
  - a poor first-pass ranking is exposed by a later confirmation surface
- `good_frontier_improves_second_pass`
  - second pass uses first-pass ranking and gets a better result with bounded
    extra activation
- `defer_is_explicit_not_missing`
  - deferred surfaces are recorded and reviewable
- `reuse_not_restart`
  - second pass reuses allowed artifacts and does not behave like a cold rerun
- `medium_band_pressure_retained`
  - the fixture remains meaningfully difficult; success is not explained by
    simplification
- `operator_useful_output_early`
  - a human can see what matters before the whole package is deeply explored

## Constraints

Preserve:

- Spectrum medium-band semantic pressure
- separate proving-lane trust work
- separate future suite work for deep interwoven state

Constrain:

- turning this into a generic speed benchmark
- treating efficiency as raw wall-clock only
- allowing it to become the cross-DLL interwoven suite by accident
- allowing pass two to smuggle in unsupported trust from pass one

## Assumptions And Defaults

- base the suite on Spectrum medium-band structure rather than inventing a new
  toy family
- keep proving-lane trust out of this suite's primary question; assume it is
  handled by a separate family
- keep deep cross-DLL interwoven initialization out of this suite's primary
  question; that gets its own family later
- treat efficiency here as workflow economics and staged activation, not mere
  runtime optimization
- document likely `gpt-4o` placement now, but do not require multi-model
  routing for v1 acceptance
- the suite's value is teaching the product how to stay organized and
  economically sane as pressure scales, not simply finishing sooner on a
  smaller case

## Questions This Suite Can Answer

- can the pipeline produce a useful first-pass operational map before deeply
  probing the full package
- can the pipeline rank a worthwhile frontier early enough to reduce wasted
  work
- can deferred surfaces be made explicit instead of being omitted or probed by
  accident
- can pass two reuse pass-one outputs instead of restarting cold
- can selective deepening reach a comparable medium-band semantic outcome with
  less unnecessary exploration
- can a new pre-pipeline system improve:
  - `time_to_useful_map`
  - `deferred_surface_count`
  - `reuse_success_rate`
  - `wasted_deep_probe_count`
- can a new stage, iteration policy, or delegation pattern improve the
  economics of medium-band work
- is the workflow becoming more disciplined as activation pressure rises

## Questions This Suite Cannot Answer

- is the pipeline efficient enough for `50 DLL / 1,000 function` estates
- is the pipeline product-scale efficient under large-package throughput
- does the same activation policy survive deep cross-DLL interwoven
  initialization pressure
- do noisy real-world archives change the workflow economics materially
- do malformed or unusual binaries change performance behavior materially
- is the production model mix cheap enough at enterprise scale
- does the system remain efficient under operator concurrency or multi-package
  queue pressure
- do medium-band efficiency gains extrapolate honestly to hard-family or
  enterprise-scale workloads

## What The Next Suite In This Category Should Add

The next efficiency suite in this category should add:

- larger-package throughput pressure
- explicit package realism and archive clutter
- stronger comparison between selective deepening and flat deeper probing
- queue or concurrency pressure where useful
- more explicit cost surfaces for model and tool routing
- a tighter compiled measurement packet for repeated benchmark comparison

It should still preserve clean failure attribution and should not absorb the
separate cross-DLL interwoven-state family by accident.
