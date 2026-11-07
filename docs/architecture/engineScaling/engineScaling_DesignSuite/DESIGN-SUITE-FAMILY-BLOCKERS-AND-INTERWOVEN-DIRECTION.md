# Design Suite: Family Blockers And Interwoven Direction

## Summary

The next proving suite should keep the same core challenge classes as Contoso,
but it should stop looking and feeling like Contoso.

The goal is not to create "Contoso with a different name." The goal is to
create a new proving family that preserves the same hard dependency problems
while changing the package shape enough to test whether the pipeline is truly
generic.

This suite should also increase pressure on interwoven dependency reasoning.
The pipeline should be forced to reason about family-level blockers, not only
local function unlocks.

## Why We Need This

Contoso is still useful, but it has limits:

- known DLL and fixture family shape
- known runtime shape
- curated ambiguity
- known business-story bias

That means the pipeline can still become very good at Contoso-shaped reasoning
without yet proving it understands generic dependency structure.

The next suite should answer a different question:

- can the same architecture still organize and solve the problem when the
  package looks different, but the dependency challenges are just as hard or
  harder?

## Core Challenge Classes To Preserve

The next suite should keep these challenge classes because they are central to
what Contoso already proves:

- producer to consumer handoffs
- shared state reuse
- staged chains
- fanout from one upstream producer into several downstream consumers
- stale or forked state risk

If the new suite loses these, it becomes easier than Contoso in the wrong way.

## Difficulty We Should Add On Top

The next suite should not just add more functions. It should add harder
dependency organization.

Add these pressures:

- competing producers for the same consumer
- partial unlocks where one prerequisite helps but does not complete the chain
- family-wide shared blockers where multiple modules stay blocked until one
  hidden state family is satisfied
- overlapping dependency families where one module plausibly belongs to more
  than one group
- cross-family contamination where the wrong token looks valid but should be
  rejected
- delayed effects where success is only visible one step later
- rollback or invalidated state where a later operation cancels earlier
  assumptions
- asymmetric visibility where one module can create state that another consumes,
  but neither describes the whole truth alone

These are more useful than simply increasing raw function count.

## What Family Group Blockers Should Mean

A family group blocker is a blocker that is not honestly attributable to one
function or one local seam. It is a blocker shared across a family of work.

The point of the next suite is to make these blockers visible enough that the
pipeline can:

- recognize them
- group them
- keep them bounded
- avoid misclassifying them as unrelated local failures

## Family Blocker Patterns To Design In

### 1. Bootstrap Family Blocker

One root state must exist before an entire family can work.

Example shape:

- `session/bootstrap`
- `billing/authorize`
- `inventory/reserve`
- `audit/commit`

Nothing downstream is honest until the bootstrap family is satisfied.

Why this matters:

- stresses initialization grouping
- stresses family-level blocker attribution
- prevents naive local retries from looking useful

### 2. Shared State Carrier Blocker

Several modules depend on the same state carrier, but each consumer needs a
different property of it.

Example:

- one consumer only needs token existence
- another needs freshness
- another needs freshness plus sequence alignment

Why this matters:

- stresses shared-state reporting
- stresses stale-state risk
- prevents simplistic "token exists, therefore valid" reasoning

### 3. Two-Family Overlap Blocker

One module sits between two dependency families and can mislead grouping.

Example:

- `orchestration/router` belongs partly to `customer-session`
- and partly to `order-commit`

Why this matters:

- stresses dependency-class inference
- stresses slice planning
- reveals whether grouping is too coarse

### 4. Forked-State Blocker

Two plausible branches of state exist, and the wrong one poisons downstream
behavior.

Example:

- reservation token A versus reservation token B
- both look syntactically valid
- only one is lineage-correct

Why this matters:

- stresses contradiction visibility
- stresses stale or forked state handling
- reveals whether the pipeline is too willing to accept lookalike state

### 5. Late-Confirmation Blocker

A module appears locally successful, but only a downstream module reveals
whether it actually worked.

Why this matters:

- stresses local-green versus package-red interpretation
- stresses package truth and later confirmation surfaces
- forces the pipeline to preserve uncertainty instead of overclaiming

### 6. Mutual-Pressure Blocker

Two families must both be partially advanced before either can fully confirm.

This should be used sparingly because it is significantly harder than the other
patterns, but it is realistic.

Why this matters:

- stresses interwoven planning
- stresses blocker attribution
- stresses boundedness discipline so the package does not collapse into one blob

## Suggested Module Family Shape

One strong starting shape would be:

- `session`
- `inventory`
- `billing`
- `fulfillment`
- `audit`
- `notifications`

Why this shape is useful:

- `session` can be the root bootstrap family
- `inventory` and `billing` can share state but consume it differently
- `fulfillment` can require alignment across more than one prior family
- `audit` can serve as the late confirmer
- `notifications` can act as a noisy side consumer that should not distort the
  main dependency graph

This is a stronger proving family than "just more hard functions."

## Design Principles For This Suite

The next suite should be built in layers.

### Keep

- the same core dependency challenge classes as Contoso
- boundedness
- reviewable artifacts
- attributable blockers

### Change

- package and business-story shape
- dependency family layout
- ambiguity distribution
- family-level blocker density

### Do Not Do

- do not create a random hard suite with no family structure
- do not expand raw function count without adding dependency organization
- do not make everything mutually dependent at once
- do not optimize for novelty over reviewability

## What This Suite Should Help Prove

If the suite is designed well, it should help answer:

- can the pipeline reason about dependency structure without leaning on Contoso
  naming and family expectations?
- can it detect family-level blockers instead of treating them as scattered
  local failures?
- can it keep interwoven ambiguity bounded and reviewable?
- can it preserve useful evidence artifacts instead of just producing more
  traces?

## What Success Looks Like

The suite is successful if it makes the pipeline stronger in these ways:

- harder dependency organization
- harder family grouping
- harder blocker attribution

It is not successful merely because it contains more modules or more functions.

## Brainstorming Direction

This note should remain a living design surface for the next proving suite.

Future additions should include:

- proposed suite names and theme directions
- candidate module families
- candidate family blockers
- what is preserved from Contoso
- what is intentionally made harder
- what would be too much complexity too early
- what the first bounded proving slice should be

The next suite should start controlled and intelligible, then grow in
interwoven complexity over time. The point is to test generic dependency
reasoning, not to create noise.

## Implementation Rails We Should Lock Now

The design direction is strong, but the next suite should not move into
implementation with only high-level blocker patterns.

These rails should be treated as starter defaults for the first proving family.
They are intended to be revised by evidence later, not treated as permanent
law.

## Starter Suite Contract

`Working suite name:`

- `Northstar Transaction Suite`

`Why this name works:`

- not Contoso-shaped
- not domain-specific enough to bias the architecture
- neutral enough to support transaction, sequencing, and state-handling proofs

`Primary purpose:`

- prove that the interwoven and decomposition systems still work when the
  package shape changes but the dependency structure remains difficult

`Non-purpose:`

- not a production adapter
- not a new live runtime lane
- not a compare or promotion surface by default
- not a broad enterprise simulation yet

## First Bounded Proving Slice

The first slice should be intentionally small.

`Default first slice:`

- `session`
- `inventory`
- `billing`

`Default first blocker pattern:`

- `bootstrap family blocker`

`Default supporting pressure:`

- one `shared state carrier blocker`

`What the first slice should prove:`

- one upstream bootstrap family can block more than one downstream family
- one shared token or state object can be consumed differently by more than one
  downstream module
- the pipeline can attribute the blocker to the family, not just to scattered
  local failures

`What the first slice should not try to prove yet:`

- mutual-pressure blockers
- large fanout
- deep staged-chain ambiguity
- full suite-wide family overlap

## Starter Module Family Shape

The first starter module set should default to:

- `session`
  - owns root bootstrap and emits the first session token
- `inventory`
  - consumes session state and produces a reservation artifact
- `billing`
  - consumes session state but requires additional freshness/sequence semantics
- `audit`
  - reserved for Prompt 02 or later as a late confirmer
- `fulfillment`
  - reserved for Prompt 02 or later as a staged-chain pressure surface
- `notifications`
  - reserved for Prompt 03 or later as a noisy side consumer

This keeps the first slice small while still leaving room to grow the suite in
ordered layers.

## Adapter-Free Default

`Adapter-free` should mean:

- the first proving family does not rely on a new external runtime adapter
- the suite should initially be source-controlled and locally executable inside
  the current repo
- the first tranche may be:
  - manifest and artifact driven only, or
  - simple local library execution backed by the same repo-native harness shape

`Default recommendation:`

- start with manifest and artifact-driven proofs first
- only add executable local modules after the contract shape is clear

`Why:`

- this keeps the suite focused on dependency structure first
- it avoids prematurely coupling the proving family to a runtime form
- it reduces the risk of building an execution adapter before the evidence
  model is stable

## Exact Artifact Mapping Defaults

The new suite should map into existing interwoven surfaces instead of creating
parallel vocabulary.

`Canonical starter artifacts:`

- `northstar-producer-consumer-report.json`
- `northstar-shared-state-report.json`
- `northstar-family-blocker-report.json`
- `northstar-interwoven-observer-summary.json`
- `northstar-expected-observed-report.json`

`Canonical starter blocker classes:`

- `bootstrap_family_blocker`
- `shared_state_carrier_blocker`
- `two_family_overlap_blocker`
- `forked_state_blocker`
- `late_confirmation_blocker`
- `mutual_pressure_blocker`

`How they map to existing systems:`

- producer-consumer artifacts should map to the existing producer-consumer
  interwoven surface
- shared-state artifacts should map to the existing shared-state surface
- family blocker reports should summarize why several local seams belong to one
  blocker family
- staged-chain surfaces should remain separate and should only be introduced
  when later slices need them
- dependency classes and frontier slices should consume these reports later,
  not be replaced by them

## Exact Repo Home Defaults

The likely module homes should default to:

- `api/pipeline/core/design_suite_taxonomy.py`
- `api/pipeline/core/design_suite_artifacts.py`
- `api/pipeline/core/design_suite_observers.py`
- `api/pipeline/core/design_suite_expected_observed.py`

`Why:`

- keeps suite-specific proving logic out of generic core modules until the model
  is proven reusable
- allows later extraction if the family becomes generic enough

## Artifact Placement Defaults

The first tranche should default to:

- canonical artifacts are `session-owned`
- no campaign-owned copies in tranche one
- no ledger changes in tranche one
- no collector changes in tranche one
- campaign or package truth should only receive summary projection later, if
  runtime adoption becomes justified

This keeps the first proving slice bounded and avoids prematurely turning the
new suite into a decision-bearing campaign surface.

## Explicit Boundary Against Existing Concepts

The new suite must not collapse into already-existing decomposition concepts.

`Family blocker` is not:

- an `initialization group`
  - because it describes a blocker shared across a family, not just a startup
    package
- a `dependency class`
  - because it is a failure or pressure explanation, not just a relationship
    category
- a `frontier slice`
  - because it explains why the work is blocked, not which work should run
    next

This distinction should be preserved in artifacts, observers, and docs.

## Measurement Contract Defaults

The suite should not be judged by "it feels harder."

`Starter success metrics:`

- clearer blocker attribution
  - one family blocker report explains at least two local failures more cleanly
    than isolated seam reports
- preserved distinction
  - family blocker reports stay distinct from init-group, dependency-class, and
    slice language
- contradiction visibility
  - ambiguous or wrong-state cases remain visible as contradiction-bearing, not
    silently normalized away
- bounded artifact volume
  - first-slice artifact family remains reviewable in one human pass
- reusable evidence
  - the first slice leaves behind artifacts that a later slice can consume
    without reinterpretation

## Retention And Inspection Defaults

`Canonical artifacts:`

- `northstar-producer-consumer-report.json`
- `northstar-shared-state-report.json`
- `northstar-family-blocker-report.json`
- `northstar-expected-observed-report.json`

`Summary-only artifact:`

- `northstar-interwoven-observer-summary.json`

`Compaction rule:`

- keep one canonical report per proving slice
- summaries may be regenerated from canonical truth
- older reports should be superseded, not duplicated endlessly

`Inspection expectation:`

- a human should be able to review the first slice without probe-log archaeology

## Compare And Promotion Boundary Defaults

The new suite should default to:

- `architecture-proof only`

That means:

- no baseline promotion from tranche one
- no overlap-comparable claim from tranche one
- no campaign-grade compare surface until runtime adoption exists and observer
  law remains stable under repeated proofs

This protects the repo from accidentally treating early suite work as stronger
evidence than it really is.

## Anti-Overfitting Rule For The New Suite

The new suite should not become "Contoso 2."

`Starter anti-overfitting checks:`

- do not reuse Contoso naming conventions
- do not copy Contoso family layout one-to-one
- do not rely on Contoso-specific DLL mental models
- do not make the business story so abstract that it stops representing real
  dependency structure
- after each tranche, write down what still looks Contoso-shaped and what no
  longer does

This should be treated as an explicit review step, not an optional concern.

## Family Blocker Observer Defaults

The first observer family should default to:

- `family_blocker_plausibility`
- `shared_state_carrier_plausibility`
- `forked_state_visibility`
- `late_confirmation_visibility`

`Starter observer payload fields:`

- `observer_name`
- `subject_ids`
- `blocker_family`
- `status`
- `contradiction_state`
- `explanation`
- `expected_behavior`
- `observed_behavior`
- `review_notes`

These payloads should stay bounded and human-readable.

## Economics Defaults

The first design suite should stay small.

`Starter size defaults:`

- `3 active modules` in the first proving slice
- `6 total modules` in the first suite family
- `12-20 functions` in the first executable proving surface

`Starter tranche discipline:`

- add only one new blocker pattern at a time
- do not introduce mutual-pressure blockers until at least one simpler family
  blocker slice is green
- do not add noisy side consumers until the bootstrap and shared-state blocker
  reports are stable

`Stop condition for overbreadth:`

- if the first slice requires more than one unrelated blocker explanation to be
  understood honestly, it is too broad and should be reduced

## Expected Versus Observed Behavior

Because this suite is source-controlled and intentionally designed, it should
also include an expected-versus-observed behavior report from the start.

`Why this matters:`

- we are no longer only reverse-analyzing opaque binaries
- we are designing the intended behavior ourselves
- that means we can encode what should happen and compare it directly to what
  the pipeline actually inferred, grouped, and reported

`Starter canonical report:`

- `northstar-expected-observed-report.json`

`Starter report fields:`

- `slice_id`
- `module_family`
- `expected_blockers`
- `expected_producers`
- `expected_consumers`
- `expected_shared_state`
- `expected_family_groups`
- `observed_blockers`
- `observed_producers`
- `observed_consumers`
- `observed_shared_state`
- `observed_family_groups`
- `mismatches`
- `overclaims`
- `underclaims`
- `notes`

This should become one of the main review surfaces for the new suite, because
it gives us a direct way to see whether the pipeline is:

- grouping correctly
- overclaiming generic understanding
- missing blocker families
- collapsing distinct concepts together

## How To Build The Expected Versus Observed Report

The report should be assembled in two passes.

### 1. Expected Side

The `expected` side should be authored directly from the suite source and its
manifests.

`Primary inputs:`

- source-controlled module definitions
- source-controlled test fixtures
- suite truth manifest
- declared blocker-family design for the active proving slice

`How to build it:`

- list the intended producers
- list the intended consumers
- list the intended shared-state carriers
- list the intended blocker families
- list the intended family memberships
- list the intended late-confirmation or staged-chain behavior if present

This should be written before the pipeline run so we know what truth we are
actually asking the system to recover.

### 2. Observed Side

The `observed` side should be emitted after running the pipeline on the active
slice.

`Primary inputs:`

- interwoven artifacts
- family blocker reports
- observer summaries
- decomposition or slice-planning outputs if they are already in scope for the
  slice

`How to build it:`

- collect what the pipeline inferred as producers
- collect what it inferred as consumers
- collect what it inferred as shared-state carriers
- collect what blocker families it emitted
- collect what family memberships it assigned
- collect where the pipeline deferred or marked contradiction

So yes, the observed side comes after we run it.

### 3. Comparison Pass

After both halves exist, compare them explicitly.

`Comparison outcomes to compute:`

- `match`
  - expected and observed align closely enough to trust the inference
- `overclaim`
  - the pipeline asserted a producer, consumer, blocker family, or grouping
    stronger than the source truth supports
- `underclaim`
  - the pipeline missed an intended dependency or family relationship
- `misgroup`
  - the right pieces were seen, but grouped into the wrong family or blocker
    explanation
- `deferred`
  - the pipeline stayed appropriately cautious and left the seam unresolved

### 4. What Good Looks Like

For the first proving slice, a good report should show:

- high agreement on the first bootstrap family blocker
- correct detection of the first shared-state carrier
- no silent overclaiming of family membership
- bounded and reviewable mismatch output

### 5. Why This Should Exist Before Implementation

The report shape should be defined now, before implementation, because it tells
us what the suite is trying to teach the pipeline.

If we wait until after the first run, the risk is that we will shape the report
around whatever the pipeline happened to emit instead of using it as an honest
measurement surface.

## What The Next Follow-Up Prompt Should Lock

Before implementation, the next bounded prompt should lock:

- exact suite name
- exact first module trio
- exact first proving slice artifact set
- exact expected-versus-observed schema
- exact first blocker family observer payload
- exact first acceptance criteria

That is the smallest honest next step from this design note.

## Prompt 00 Review

What was locked:

- the suite contract now exists in code in:
  - `api/pipeline/core/design_suite_taxonomy.py`
- the first bounded slice remains:
  - `session`
  - `inventory`
  - `billing`
- the first blocker family remains:
  - `bootstrap_family_blocker`
- the supporting pressure remains:
  - `shared_state_carrier_blocker`
- the expected-versus-observed schema now exists in:
  - `api/pipeline/core/design_suite_expected_observed.py`

What changed:

- the suite is no longer only a brainstorming note
- the first bounded thresholds and artifact boundaries are now machine-readable

What remains deferred:

- executable runtime form
- campaign/runtime adoption
- compare/promotion use

## Prompt 01 Review

What was added:

- a source-controlled proving family now exists under:
  - `tests/fixtures/design_suite/northstar_transaction_suite/`
- the first source scaffold now includes:
  - `session.py`
  - `inventory.py`
  - `billing.py`
  - deferred:
    - `audit.py`
    - `fulfillment.py`
    - `notifications.py`
- the first authored expected report now exists in:
  - `tests/fixtures/design_suite/northstar_transaction_suite/northstar-expected-observed-report.json`

What Contoso no longer has to carry alone:

- the role of a source-controlled, non-Contoso proving family

## Prompt 02 Review

What was added:

- first design-suite artifacts now exist in:
  - `api/pipeline/core/design_suite_artifacts.py`
- first design-suite observers now exist in:
  - `api/pipeline/core/design_suite_observers.py`

What the first artifact family now proves:

- producer-consumer reporting can transfer to a non-Contoso proving family
- shared-state reporting can transfer to a non-Contoso proving family
- family-blocker reporting can be bounded and explicit instead of purely
  interpretive

## Prompt 03 Review

What was added:

- the first observed run and expected-versus-observed comparison now exist in:
  - `api/pipeline/core/design_suite_expected_observed.py`

What this proves:

- the suite now has a real measurement surface
- observed output can be assembled from emitted artifacts instead of hand
  interpretation
- supersession and canonical-current-report behavior exist for later runs on the
  same slice

## Prompt 04 Review

What was added:

- bounded overlap pressure using the `audit` module
- the first `two_family_overlap_blocker` seam

What this proves:

- the suite can increase family ambiguity without broadening into a full new
  package
- misgroup pressure can be added while keeping the suite bounded to four active
  modules

What remains intentionally deferred:

- `notifications`
- mutual-pressure blockers
- broad noisy side-consumer pressure

## Prompt 05 Review

What was added:

- the tranche now closes with:
  - `docs/architecture/engineScaling/engineScaling_DesignSuite/DESIGN-SUITE-TRANSFER-REVIEW.md`

What this proves:

- the repo now has a second proving-family direction that is not just Contoso
  with a new name
- the next branch can be chosen from evidence instead of from broad future-road
  speculation

Current honest closeout:

- the design-suite chain is now implemented as an architecture-proof proving
  surface
- the remaining gap is no longer "there is no non-Contoso proving family"
- the remaining gap is choosing the next bounded blocker-pattern branch before
  any runtime or product broadening

## Late-Confirmation Follow-Up Review

What was added:

- a bounded `late_confirmation_blocker` expansion using the existing `audit`
  module
- explicit `confirmation_sites` and `provisional_subjects` inside the
  Northstar family-blocker artifact
- a dedicated `late_confirmation_visibility` observer
- expected-versus-observed confirmation-site comparison in:
  - `api/pipeline/core/design_suite_expected_observed.py`

What this proves:

- the Northstar suite can represent downstream confirmation explicitly instead
  of treating upstream local success as fully trusted by default
- expected-versus-observed reporting can now distinguish:
  - upstream provisional subjects
  - downstream confirmation sites
- the suite can add a deeper blocker pattern while staying bounded to the same
  four-module shape:
  - `session`
  - `inventory`
  - `billing`
  - `audit`

What remains intentionally deferred:

- forked-state pressure
- mutual-pressure families
- runtime/package adoption for the design suite

Current honest next move:

- the next bounded blocker-pattern branch should now be:
  - `forked_state_blocker`
- that should come before any design-suite runtime or product broadening so we
  can test lineage correctness and contradiction visibility under the same
  expected-versus-observed surface

## Forked-State Follow-Up Review

What was added:

- a bounded `forked_state_blocker` expansion using the same `audit`-backed
  Northstar shape
- explicit `lineage_branches`, `accepted_branch`, and `rejected_branches`
  inside the Northstar family-blocker artifact
- a dedicated `forked_state_visibility` observer
- expected-versus-observed branch comparison in:
  - `api/pipeline/core/design_suite_expected_observed.py`

What this proves:

- the Northstar suite can represent lookalike state branches explicitly instead
  of collapsing them into generic shared-state reuse
- expected-versus-observed reporting can now distinguish:
  - all plausible lineage branches
  - the one accepted branch
  - branches that should be rejected even when they look syntactically valid
- the suite now carries:
  - overlap pressure
  - late-confirmation pressure
  - forked-state pressure
  under the same bounded four-module proving surface

What remains intentionally deferred:

- mutual-pressure families
- a second non-Northstar proving family
- runtime/package adoption for the design suite

Current honest next move:

- the next bounded move should no longer be "add another blocker by default"
- the next honest move is a bounded design-suite runtime/package adoption
  tranche so the new blocker methodology becomes a transfer surface instead of
  remaining fixture-local only

## Runtime/Package Adoption Review

What was added:

- a reusable local design-suite runtime bridge in:
  - `api/pipeline/core/design_suite_runtime_bridge.py`
- a local serialized runtime runner in:
  - `scripts/runs/run_design_suite_runtime_adoption.py`
- session-owned runtime/package artifacts:
  - `design-suite-runtime-plan.json`
  - `design-suite-package-truth.json`
  - `design-suite-cohesion-report.json`
  - `design-suite-execution-trace.json`
- source-authored execution inputs and execution rules inside the Northstar
  truth manifest

What this proves:

- Northstar is no longer fixture-local only
- the blocker-family surfaces now survive into a local runtime/package summary
- the suite can project:
  - provisional subjects
  - confirmation sites
  - lineage branches
  - accepted and rejected branches
  into a package-like truth/cohesion surface without using campaign truth or
  campaign cohesion

What remains intentionally deferred:

- campaign runner integration
- campaign truth/cohesion emission
- compare/promotion readiness
- ledger and collector schema expansion

Current honest next move:

- the remaining gap is no longer "Northstar has no runtime/package transfer
  surface"
- the next honest move is deciding whether to:
  - keep design suites as local runtime transfer surfaces only, or
  - start one bounded campaign-shaped local adoption tranche

## Prompt 06 Review

What was added:

- a local campaign-shaped rehearsal layer in:
  - `api/pipeline/core/design_suite_campaign_local.py`
- a bounded local campaign-shaped runner in:
  - `scripts/runs/run_design_suite_campaign_local.py`
- session-owned local campaign-shaped artifacts under:
  - `sessions/design_suite/campaign_local/<suite>/<timestamp>/`

What this proves:

- Northstar can now rehearse campaign-shaped truth and cohesion locally without
  using the real campaign runner
- the local rehearsal keeps:
  - provisional subjects
  - confirmation sites
  - lineage branches
  - accepted and rejected branches
  intact under a campaign-shaped surface
- the suite is still architecture-proof only:
  - no compare readiness
  - no promotion readiness
  - no ledger or collector expansion

What remains intentionally deferred:

- engine-scaling projection of the local campaign-shaped plan
- campaign readiness gating
- one bounded real Northstar campaign

Current honest next move:

- project the new local campaign-shaped Northstar surfaces into the engine-
  scaling layer before spending real campaign complexity

## Prompt 07 Review

What was added:

- a Northstar scaling adapter in:
  - `api/pipeline/core/design_suite_scaling_projection.py`
- a scaling runner in:
  - `scripts/runs/run_design_suite_scaling_projection.py`
- session-owned scaling artifacts:
  - `design-suite-scaling-projection.json`
  - `design-suite-slice-plan.json`
  - `design-suite-scaling-cohesion.json`

What this proves:

- Northstar can now pass through the repo's package-frontier, decomposition,
  and slice-attribution surfaces without losing its family-blocker identity
- family blockers remain explanatory pressure surfaces instead of collapsing
  into initialization groups, dependency classes, or frontier slices
- provisional subjects, confirmation sites, and forked-state branch visibility
  survive the scaling projection wrapper

Current honest next move:

- build the readiness gate now that local campaign shape and scaling projection
  are both real and reviewable

## Prompt 08 Review

What was added:

- a Northstar campaign readiness builder in:
  - `api/pipeline/core/design_suite_campaign_readiness.py`
- a readiness runner in:
  - `scripts/runs/run_design_suite_campaign_readiness.py`
- a machine-readable readiness artifact:
  - `northstar-campaign-readiness.json`

What this proves:

- Northstar campaign eligibility is now explicit instead of judgment-based
- `late_confirmation` is locked as the first bounded campaign mode
- `forked_state` remains a mandatory local guard even though it is not the
  first campaign mode

Current honest next move:

- run one bounded real Northstar campaign while keeping compare and promotion
  blocked

## Prompt 09 Review

What was added:

- a bounded Northstar campaign runtime wrapper in:
  - `api/pipeline/core/design_suite_campaign_runtime.py`
- one first bounded real campaign entrypoint in:
  - `scripts/runs/run_northstar_campaign.py`
- one real bounded Northstar campaign under:
  - `sessions/campaigns/northstar-20260407-230410/`

What this proves:

- Northstar is no longer only a local rehearsal surface
- the repo now has one bounded campaign-bearing design-suite proof
- the campaign preserves:
  - provisional subjects
  - confirmation sites
  - family blocker IDs
  while still keeping:
  - `compare_ready = false`
  - `promotion_ready = false`

Current honest next move:

- the next bounded branch should be:
  - tighten the campaign seam first if broader reuse needs cleaner shared
    primitives, or
  - a `forked_state` campaign if the next question is whether branch-lineage
    pressure survives the same campaign-bearing path

## Forked-State Campaign Review

What was added:

- forked-state branch preservation in the bounded Northstar campaign runtime:
  - `lineage_branches`
  - `accepted_branches`
  - `rejected_branches`
- mode-aware readiness gating for `forked_state`
- one bounded real forked-state campaign under:
  - `sessions/campaigns/`

What this proves:

- the real campaign-bearing path can now preserve accepted versus rejected
  branch lineage without normalizing the split away
- `forked_state` semantics survive into:
  - `campaign/campaign-truth.json`
  - `audits/campaign-cohesion-report.json`
  - `audits/northstar-campaign-attribution-review.json`
- compare and promotion remain blocked while the campaign seam learns a harder
  semantic pressure

What remained awkward:

- the campaign-bearing path still uses a Northstar-specific wrapper
- the semantic projection is now honest, but not yet generalized into a
  reusable design-suite campaign seam

Current honest next move:

- tighten and genericize the campaign seam from evidence rather than adding a
  second suite immediately

## Prompt 10 Review

What was added:

- the smallest reusable campaign-bearing design-suite seam is now explicit in:
  - `api/pipeline/core/design_suite_campaign_runtime.py`
- a bounded reusable seam artifact now exists:
  - `design-suite-reusable-campaign-seam.json`
- the bounded Northstar campaign runner now emits that seam artifact in real
  campaign output

What this proves:

- campaign truth projection is no longer only an informal Northstar helper
- campaign cohesion projection is no longer only an informal Northstar helper
- campaign attribution preservation is no longer only an informal Northstar
  helper
- both `late_confirmation` and `forked_state` can pass through the same
  extracted seam while compare and promotion remain blocked

What changed in the architecture:

- the repo now has an explicit reusable design-suite campaign projection layer
  inside the Northstar campaign runtime owner
- one real seam bug was fixed during reproof:
  - distinct campaign runs no longer collide on the same campaign id when
    launched within the same second

What remains unproven:

- a future harder suite has not yet inherited this seam in practice
- the entrypoint wrapper is still Northstar-specific even though the semantic
  projection layer is tighter

Current honest next move:

- reprove both campaign modes through the tightened seam and decide whether the
  pathway is ready for a harder post-Northstar suite

## Prompt 11 Review

What was added:

- a bounded campaign-seam evaluation builder in:
  - `api/pipeline/core/design_suite_campaign_evaluation.py`
- a seam evaluation runner in:
  - `scripts/runs/run_design_suite_campaign_seam_evaluation.py`
- a machine-readable evaluation artifact:
  - `design-suite-campaign-seam-evaluation.json`

What this proves:

- both current Northstar campaign modes remain green through the tightened seam
- the reusable campaign seam is present across:
  - truth projection
  - cohesion projection
  - attribution preservation
- the pathway is now ready for a harder post-Northstar suite at the contract
  level without broadening compare or promotion

What changed in the architecture:

- the wider Northstar goal is now satisfied:
  - Northstar is no longer only a proving family with campaign glue
  - it is now a proving family that has produced a reusable design-suite
    campaign pathway

What remains unproven:

- a successor suite has not yet been contract-defined or built
- the remaining Northstar-only glue still needs explicit keep/narrow/
  supersede/retire treatment in later work

Current honest next move:

- write the successor-suite contract and inheritance gate prompt next rather
  than broadening Northstar pressure further

## Current Broader Goal

The current broader overnight goal is:

- turn the reusable Northstar pathway into a second-suite-ready design-suite
  architecture by:
  - defining the first harder successor suite
  - implementing its first bounded slice
  - carrying that slice to bounded local campaign-shaped readiness
  - while keeping compare and promotion blocked

The current conditional stretch goal after that is:

- begin weakness-register triage and reduction only if:
  - the successor suite reaches bounded local campaign-shaped readiness
  - and no stronger implementation blocker remains

Why this is the right horizon now:

- Northstar has already proved the reusable campaign seam
- the next honest question is whether that seam can survive inheritance into a
  harder suite
- weakness-register cleanup is valuable, but only after the active proving
  branch stops being the stronger blocker

## Prompt 12 Review

What was added:

- a successor-suite contract owner in:
  - `api/pipeline/core/design_suite_successor_contract.py`
- a concrete successor contract artifact under:
  - `tests/fixtures/design_suite/atlas_reconciliation_suite/successor-suite-contract.json`

What this proves:

- the post-Northstar suite is now explicit instead of implicit brainstorming
- the harder pressure family is locked:
  - `mutual_pressure_blocker`

What remains unproven:

- the contract still needed a real bounded slice
- the successor suite still needed local proof surfaces

## Prompt 13 Review

What was added:

- the Atlas successor suite fixture family under:
  - `tests/fixtures/design_suite/atlas_reconciliation_suite/`
- the first bounded slice and expected report:
  - `successor-suite-first-slice.json`
  - `atlas-expected-observed-report.json`

What this proves:

- the harder post-Northstar suite is real as source and expected truth
- the harder pressure is structural, not just renamed Northstar semantics

What remains unproven:

- local runtime/package survival
- local campaign-shaped readiness

## Prompt 14 Review

What was added:

- an Atlas local runtime/package runner in:
  - `scripts/runs/run_atlas_successor_runtime_adoption.py`
- a suite-specific helper owner in:
  - `api/pipeline/core/atlas_successor_suite.py`

What this proves:

- the reusable runtime/package seam now survives on a second, harder suite
- the successor suite is no longer fixture-local only

What remains unproven:

- local campaign-shaped readiness on the harder suite

## Prompt 15 Review

What was added:

- an Atlas local campaign-shaped readiness runner in:
  - `scripts/runs/run_atlas_successor_campaign_local.py`
- one real bounded local readiness output under:
  - `sessions/design_suite/campaign_local/atlas_reconciliation_suite/`

What this proves:

- the reusable Northstar pathway has now survived inheritance into a second
  suite and reached bounded local campaign-shaped readiness
- the broader successor-suite goal is met without broadening compare or
  promotion

What remains unproven:

- whether the next honest move is:
  - real bounded campaign admission for the successor suite
  - or more generic campaign-seam tightening first

Current honest next move:

- treat that post-readiness choice as the stronger blocker
- do not start weakness-register triage yet because a stronger implementation
  blocker still remains

## Prompt 16 Review

What was added:

- a machine-readable successor-suite branch decision owner in:
  - `api/pipeline/core/design_suite_branch_decision.py`
- a runner in:
  - `scripts/runs/run_successor_suite_branch_decision.py`
- one real branch artifact under:
  - `sessions/design_suite/branch_decision/atlas_reconciliation_suite/`

What this proves:

- the next blocker after Atlas local readiness is explicit
- the repo should not start weakness-register triage yet
- the stronger blocker is:
  - generic real campaign seam tightening

What remains unproven:

- whether Atlas can survive a real bounded campaign once the real campaign seam
  is genericized

Current honest next move:

- genericize the real campaign seam first
- then gate Atlas for a real bounded campaign

## Prompt 17 Review

What was added:

- a generic real campaign contract owner in:
  - `api/pipeline/core/design_suite_real_campaign_contract.py`
- a contract artifact in:
  - `docs/architecture/engineScaling/engineScaling_DesignSuite/design-suite-real-campaign-contract.json`

What this proves:

- the real campaign seam is no longer only implied by runner behavior
- generic ownership, artifact inheritance, and non-compare boundaries are now
  explicit and machine-readable

What remains unproven:

- the contract still needed a real generic runtime owner
- Atlas still had not been admitted through that owner

## Prompt 18 Review

What was added:

- a generic real campaign runtime owner in:
  - `api/pipeline/core/design_suite_real_campaign_runtime.py`
- a generic runner in:
  - `scripts/runs/run_design_suite_real_campaign.py`
- backward-tolerant suite-specific wrappers:
  - `scripts/runs/run_northstar_campaign.py`
  - `scripts/runs/run_atlas_campaign.py`

What this proves:

- Northstar no longer owns the real campaign runtime by itself
- the generic owner can preserve:
  - bounded campaign truth
  - campaign cohesion
  - campaign attribution review
- both existing Northstar real-campaign modes remain green through the
  extracted owner

What remains unproven:

- whether Atlas is honestly ready for one real bounded campaign through the
  generic owner

## Prompt 19 Review

What was added:

- a generic real campaign readiness writer in:
  - `api/pipeline/core/design_suite_real_campaign_readiness.py`
- a readiness runner in:
  - `scripts/runs/run_design_suite_real_campaign_readiness.py`
- one real readiness artifact under:
  - `sessions/design_suite/campaign_readiness/atlas_reconciliation_suite/20260408-071909/atlas-real-campaign-readiness.json`

What this proves:

- Atlas campaign admission is now explicit and machine-readable
- the first real Atlas campaign mode is locked:
  - `mutual_pressure`
- the admission surface remains architecture-proof only:
  - `compare_ready = false`
  - `promotion_ready = false`

What remains unproven:

- whether Atlas mutual-pressure semantics survive into a real bounded campaign

## Prompt 20 Review

What was added:

- one real bounded Atlas campaign under:
  - `sessions/campaigns/atlas_reconciliation_suite-20260408-071909-470866-mutual_pressure/`

What this proves:

- the generic real-campaign seam now survives on a harder successor suite
- Atlas mutual-pressure semantics survive into:
  - `campaign/campaign-truth.json`
  - `audits/campaign-cohesion-report.json`
  - `audits/design-suite-campaign-attribution-review.json`
- compare and promotion remain blocked during the run

What remains unproven:

- whether any stronger implementation blocker still outranks weakness-register
  triage after the real campaign result

## Prompt 21 Review

What was added:

- a post-campaign transfer review owner in:
  - `api/pipeline/core/design_suite_post_campaign_review.py`
- a runner in:
  - `scripts/runs/run_design_suite_post_campaign_review.py`
- one post-campaign branch artifact under:
  - `sessions/campaigns/atlas_reconciliation_suite-20260408-071909-470866-mutual_pressure/audits/design-suite-post-campaign-review.json`

What this proves:

- the Atlas real-campaign result does not leave a stronger implementation
  blocker ahead of the conditional stretch goal
- the next honest move is now:
  - weakness-register triage and reduction

What changed in the architecture:

- the design-suite campaign pathway is now proven across:
  - Northstar real bounded campaigns
  - Atlas real bounded campaign
- the next scaling pressure is no longer proving the design-suite campaign
  seam, but reducing the now-larger architectural weakness surface into a
  smaller decision-bearing set

Current honest next move:

- activate the conditional stretch goal:
  - weakness-register triage and reduction

## Prompt 22 Review

What was added:

- a weakness-triage owner in:
  - `api/pipeline/core/weakness_register_triage.py`
- a runner in:
  - `scripts/runs/run_weakness_register_triage.py`
- one real triage artifact under:
  - `sessions/architecture/weakness_register_triage/20260408-105053/weakness-register-triage.json`

What this proves:

- the conditional stretch goal was worth doing, because it did not devolve
  into generic cleanup
- the weakness register can now steer the next branch from a smaller active set
  instead of a long undifferentiated list
- the next blocker after design-suite proof is not design-suite-local:
  - it is the live package-floor validity seam

What changed in the architecture:

- a machine-readable weakness triage layer now exists
- stale or duplicated repo surfaces are now named explicitly enough to stop
  silently taxing operator efficiency

Current honest next move:

- follow the triage result into:
  - `23-package-floor-live-validity-and-replay-gate.md`

## Prompt 23 Review

What this proved:

- the live package-floor validity seam is now explicit and machine-readable
- the reduced Batch B rerun on campaign `46fe7b2f` is trustworthy enough for
  a reduced package-floor comparable claim
- replay freshness and entry-surface choice are no longer the active blocker
  on that lane

What changed in the architecture:

- design-suite work is no longer the strongest active branch
- the current branch priority is now the strongest trusted Contoso frontier
  loss itself, starting with `contoso_config.dll` environment-gating

Current honest next move:

- `24-config-frontier-environment-gate-repair.md`
