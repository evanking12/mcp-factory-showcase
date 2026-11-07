# Interwoven Methodology And Generic System Direction

## Summary

This document is now the **main prompt and dynamic review surface** for
interwoven expansion.

It combines two responsibilities that previously lived separately:

- the architecture direction for building a generic interwoven system
- the standing review surface for asking, after each tranche:
  - what current Contoso proved
  - what synthetic stress exposed
  - what must be added next to the suite
  - what changed in the generic model

The governing question is:

> how do we build a generic interwoven-dependency system without losing control?

The governing method is:

- start small
- verify the smallest useful interwoven behavior first
- change one major variable at a time
- append findings after each tranche
- only broaden the proving ground when the current layer is explicit,
  reviewable, and still honest under stress

This is the right next move because the repo now has:

- decomposition rails
- shard intake and merge
- initialization-group inference
- dependency-class inference
- frontier slicing
- slice execution coordination
- decomposition-native reduced campaign support

What it does **not** yet have is a first-class generic system for interwoven
dependency behavior that can scale from easy Contoso cases to harder
enterprise-like cases without turning into prompt memory or manual
interpretation.

## Plain-English Goal

We want the pipeline to stop treating interwoven dependency behavior as a
surprising special case and start treating it as a normal, explicit, testable
planning surface.

At maturity, the system should be able to say:

- who produced the state
- who consumed it
- whether the dependency is direct, staged, or shared-state mediated
- whether the correct unit is:
  - a producer-consumer pair
  - an initialization group
  - a dependency class
  - a staged interwoven chain
  - one frontier slice
  - several frontier slices in order
- what truth can be frozen
- what truth must stay live
- what must be rerun together
- what should stay deferred

The end state is not just a better research workflow. It is a product-capable
generic system that can be automated safely.

## Core Operating Principle

The operating principle is:

- **change one important variable at a time**

Right now that variable is:

- **interwoven dependency complexity**

We should not simultaneously:

- broaden to many new package families
- redesign decomposition again
- chase raw remaining-function count as the main metric
- add wide live scale before interwoven control exists

The correct method is:

1. prove the easiest interwoven cases we already have
2. define the smallest useful taxonomy
3. turn that taxonomy into artifacts and observers
4. stress it synthetically while staying bounded
5. feed it into runtime and package planning
6. only then expand the proving ground deliberately

## Why Start With Contoso

Contoso is still the right proving ground for this phase because it lets us
hold most variables still while changing one:

- the interwoven dependency model

That means:

- package family stays familiar
- runtime surfaces are already known
- reduced campaigns are already possible
- if something breaks, we have a much better chance of knowing whether it was:
  - the taxonomy
  - the artifact surface
  - the observer law
  - runtime adoption
  - or the interwoven assumption itself

This is the right control strategy.

We are not trying to prove enterprise readiness by leaving Contoso
immediately. We are trying to extract the maximum **generic methodology** from
Contoso before broader expansion.

## What Interwoven Should Mean

Interwoven should not remain a vague label.

The first generic vocabulary should include at least:

- `producer`
  - a function, DLL, or slice that emits state another seam needs

- `consumer`
  - a function, DLL, or slice whose success depends on upstream state

- `shared_state_carrier`
  - a reusable state surface consumed by several downstream seams

- `cross_dll_initialization_group`
  - a bounded initialization package whose effects unlock several DLLs or
    function families

- `interwoven_dependency_class`
  - a broader relationship family that spans more than one local state package

- `staged_interwoven_chain`
  - an ordered chain where correctness depends on sequence, not just
    membership

- `interwoven_frontier_slice`
  - a bounded active work slice whose correctness depends on one or more
    interwoven structures above

These concepts are related, but they are not interchangeable.

## Main Prompt

When we implement the interwoven system, the work should proceed in this exact
priority order.

Each phase should:

- start with the smallest bounded target
- verify locally first
- update this document after the tranche
- only then move to the next phase

### Phase 1. Interwoven Taxonomy Pass

`Goal:`
- define the smallest useful generic categories for interwoven behavior

`Why This Comes First:`
- without stable vocabulary, every later proof will drift

`What To Build:`
- canonical definitions for:
  - producer
  - consumer
  - shared-state carrier
  - cross-DLL initialization group
  - interwoven dependency class
  - staged interwoven chain
  - interwoven frontier slice

`What Current Contoso Should Prove:`
- that these categories are distinct enough to map onto current fixture seams

`Verification:`
- documentation review
- schema placeholder review
- at least one Contoso mapping example per category

`Done Means:`
- future prompts can use these terms without redefining them

### Phase 2. Easy Interwoven Contoso Proofs

`Goal:`
- prove the simplest real interwoven cases using existing Contoso surfaces

`Why This Comes Now:`
- it changes only one major variable and keeps the proving ground controlled

`What To Build:`
- bounded proofs for:
  - one producer -> one consumer
  - one producer -> several consumers
  - one shared-state carrier reused across DLLs
  - one simple staged chain

`What Current Contoso Should Prove:`
- that the easiest real interwoven seams can be identified without ambiguity

`Verification:`
- fixture-local tests
- explicit artifact examples
- observer pass/fail review

`Done Means:`
- interwoven behavior exists as real bounded evidence, not just as intuition

### Phase 3. Interwoven Artifact And Observer Pass

`Goal:`
- turn the taxonomy and easy proofs into explicit artifacts and observers

`Why This Comes Now:`
- without artifacts and observers, later stress results will still depend on
  human interpretation

`What To Build:`
- interwoven dependency report
- staged chain report
- shared-state reuse observer
- producer-consumer attribution artifact
- interwoven initialization contract artifact

`What Current Contoso Should Prove:`
- that the interwoven seams can be explained without probe-log archaeology

`Verification:`
- artifact schema tests
- observer payload tests
- backward-tolerant reader tests if new canonical fields are added

`Done Means:`
- interwoven behavior is now a contract-bearing system surface

### Phase 4. Bounded Synthetic Interwoven Stress

`Goal:`
- make the interwoven model survive harder ambiguity than current Contoso
  naturally provides

`Why This Comes Now:`
- the taxonomy and artifacts should be stressed before runtime adoption

`What To Build:`
- synthetic bounded cases for:
  - ambiguous shared state
  - two plausible producers
  - overlapping staged chains
  - one dependency class spanning several candidate slices
  - stale or forked state artifacts

`What Current Contoso Should Prove:`
- that the base model is coherent enough to withstand synthetic pressure

`Verification:`
- synthetic proof tests
- contradiction-preservation review
- boundedness review

`Done Means:`
- the system fails explicitly and reviewably when ambiguity is real, rather
  than passing by collapse

### Phase 5. Runtime And Package Adoption

`Goal:`
- feed interwoven structures into runtime and package planning

`Why This Comes Now:`
- runtime adoption should happen only after the artifact and observer surfaces
  are stable enough to trust

`What To Build:`
- interwoven artifacts into package planning
- interwoven structures into slice selection
- interwoven structures into runtime orchestration
- preserved lower-floor truth plus active interwoven frontier logic

`What Current Contoso Should Prove:`
- that runtime can consume interwoven planning without collapsing back into
  DLL-first behavior

`Verification:`
- bounded runtime adoption tests
- campaign truth/cohesion checks
- lane-safe reduced live proof only when local observers are green

`Done Means:`
- interwoven handling becomes part of normal package execution

### Phase 6. Targeted Contoso Suite Expansion

`Goal:`
- expand Contoso only where interwoven methodology says the suite is still too
  weak

`Why This Comes Now:`
- expansion should be evidence-driven, not blind

`What To Build:`
- new Contoso-adjacent cases only for missing interwoven patterns such as:
  - multi-hop state production
  - producer ambiguity
  - competing consumers
  - partially overlapping chains
  - stale shared-state carriers

`What Current Contoso Should Prove:`
- which interwoven shapes are already covered and which are not

`Verification:`
- new fixture or synthetic coverage added only for underrepresented patterns
- explicit before/after coverage rationale in this document

`Done Means:`
- suite growth stays disciplined and tied to methodology gaps

### Phase 7. Harder Fixture Families And Product Transfer

`Goal:`
- move from Contoso-grounded methodology to broader product-relevant proving

`Why This Comes Last:`
- broader proving is only useful once the generic model is explicit and
  reviewable

`What To Build:`
- harder fixture families
- noisier package shapes
- early transfer hypotheses for non-Contoso domains

`What Current Contoso Should Prove:`
- that the generic model is mature enough to be worth testing elsewhere

`Verification:`
- one new proving family at a time
- explicit transfer-risk review
- no broad live ambition until bounded proofs stay honest

`Done Means:`
- the interwoven model is no longer Contoso-shaped by default

## Dynamic Review Requirement

This document must be updated after each interwoven tranche.

Use this template:

### Tranche `<id>` Review

- `What current Contoso proved:`
- `What synthetic interwoven stress exposed:`
- `What changed in the generic model:`
- `What must be added next to the suite:`
- `What would count as failure if we ignore this now:`
- `What downstream phase would be poisoned by ignoring it:`
- `Did this reveal a weakness worth tightening in the weakness register?`

If the tranche changes architecture semantics materially, also review:

- `.agents/ARCHITECTURAL-WEAKNESSES.md`
- `docs/architecture/engineScaling/engineScaling_PipelineIterations/BOA-CONSTRICTOR-PACKAGE-DECOMPOSITION.md`
- `docs/architecture/engineScaling/engineScaling_PipelineIterations/BOA-CONSTRICTOR-SYSTEM-CONTRACTS.md`

## Tranche Reviews

### Prompt 00 Review

- `What current Contoso proved:`
  - the config licensed-ticket bootstrap can now be expressed as explicit
    producer-consumer evidence into both reporting and pricing seams
  - the events session/mask family can now be expressed as shared-state reuse
    without collapsing into broader dependency-class language
  - the workflow handle/nonce chain is real enough to keep as the first staged
    candidate, but it was not required to make the first artifact family
    honest
- `What synthetic interwoven stress exposed:`
  - none yet; Prompt 00 stayed on real fixture seams only
- `What changed in the generic model:`
  - the first interwoven contract surface now exists in code through:
    - taxonomy
    - producer-consumer artifacts
    - shared-state artifacts
    - first observer summaries
  - the first starter module homes are now real:
    - `api/pipeline/core/interwoven_taxonomy.py`
    - `api/pipeline/core/interwoven_artifacts.py`
    - `api/pipeline/core/interwoven_observers.py`
- `What must be added next to the suite:`
  - no new fixture family yet
  - next bounded move is staged-chain follow-up on the workflow seam and then
    synthetic ambiguity, not broad suite growth
- `What would count as failure if we ignore this now:`
  - if we pretend staged-chain is already solved without proving the workflow
    order-sensitive seam explicitly
  - if we treat the first producer/shared-state artifacts as sufficient for all
    interwoven shapes without synthetic pressure
- `What downstream phase would be poisoned by ignoring it:`
  - Prompt 01 would either overbuild staged-chain or ignore it for too long
  - Prompt 03 runtime adoption would inherit false confidence about artifact
    sufficiency
- `Did this reveal a weakness worth tightening in the weakness register?`
  - yes; the remaining interwoven weakness is now narrower: starter defaults
    are no longer missing, but staged-chain and later runtime usage still need
    bounded proof

### Prompt 01 Review

- `What current Contoso proved:`
  - the workflow seam is ordered enough to justify a real staged-chain surface
  - `workflow_reservation_bootstrap` plus
    `workflow_reservation_open_state` give a bounded chain from reservation
    creation into confirm and commit consumers
- `What synthetic interwoven stress exposed:`
  - none yet; Prompt 01 still stayed on the real workflow seam
- `What changed in the generic model:`
  - staged-chain is no longer just a documented candidate
  - the interwoven artifact family now includes
    `interwoven-staged-chain-report.json`
  - the interwoven observer family now includes
    `staged_chain_ordering_plausibility`
- `What must be added next to the suite:`
  - no new fixture family yet
  - the next bounded move is synthetic ambiguity pressure over:
    - competing producers
    - ambiguous shared state
    - overlapping chains
    - stale or forked state
- `What would count as failure if we ignore this now:`
  - if we treat workflow ordering as solved without ambiguity pressure
  - if staged-chain starts collapsing back into init-group or dependency-class
    language
- `What downstream phase would be poisoned by ignoring it:`
  - Prompt 02 would under-stress a now-real staged-chain artifact family
  - Prompt 03 would inherit ordering semantics that were never tested under
    contradiction or uncertainty
- `Did this reveal a weakness worth tightening in the weakness register?`
  - yes; the gap is no longer missing staged-chain schema, but ambiguity and
    later runtime consumption of the staged-chain surface

## How To Build Up The Contoso Suite And Verify As We Go

The Contoso suite should not be expanded broadly all at once.

The correct rule is:

- expand only when current Contoso plus synthetic stress no longer covers the
  next interwoven question honestly

That means this sequence:

1. use current Contoso to define the smallest useful interwoven model
2. add synthetic stress on top of current Contoso
3. identify which interwoven pattern is still missing
4. add the narrowest new Contoso-adjacent fixture or synthetic case for that
   missing pattern
5. verify that the new case teaches something the previous suite could not
6. update this document with what changed

Contoso expansion should therefore answer:

- what interwoven pattern was missing?
- why could synthetic stress alone not cover it?
- what is the narrowest new case that covers it?
- what observer or artifact should now become stronger because of it?

If we cannot answer those, the suite is probably expanding too early.

## Strengths Of This Direction

- It keeps the system controlled while complexity rises.
- It uses the existing decomposition architecture instead of replacing it.
- It turns interwoven dependency from a vague idea into a generic product
  direction.
- It keeps suite expansion evidence-driven.
- It creates a standing review surface so findings do not live only in chat.

## Weaknesses And Risks In Scope

### 1. Interwoven Taxonomy Drift

`Weakness:`
- producer, consumer, initialization group, dependency class, staged chain,
  and frontier slice can drift together if we do not keep their boundaries
  explicit

`Why It Matters:`
- planning collapses when all groupings become synonyms

`Starter Guardrail:`
- every new interwoven artifact must declare which category it belongs to and
  what it is not

### 2. Contoso Overfit Risk

`Weakness:`
- a model can look generic while still only matching familiar Contoso topology

`Why It Matters:`
- that creates false product confidence

`Starter Guardrail:`
- every tranche review must say what enterprise pressure still remains
  unproven

### 3. Attribution-Without-Execution Risk

`Weakness:`
- the repo is currently better at proving cross-DLL attribution than at
  executing interwoven structures as first-class runtime objects

`Why It Matters:`
- automation remains weaker than the artifacts suggest

`Starter Guardrail:`
- do not call the interwoven model mature until runtime and package planning
  can consume it directly

### 4. Synthetic Stress Without Runtime Follow-Through

`Weakness:`
- synthetic proofs can become an isolated test island if runtime adoption does
  not follow

`Why It Matters:`
- the system may appear robust in tests while live behavior still collapses

`Starter Guardrail:`
- every major synthetic proof phase must name the exact runtime seam it is
  protecting next

### 5. Artifact Explosion And Inspection Debt

`Weakness:`
- interwoven artifacts can multiply quickly: producer-consumer reports,
  staged-chain reports, shared-state reports, dependency reports, observers

`Why It Matters:`
- humans and analysis agents lose visibility if every new surface is canonical
  and none are summarized

`Starter Guardrail:`
- classify interwoven outputs early into:
  - canonical truth
  - summary-only inspection
  - synthetic proof support

### 6. Suite Expansion Without Exit Criteria

`Weakness:`
- it is easy to keep adding cases without a clear rule for what the suite is
  now proving

`Why It Matters:`
- repo complexity grows faster than architectural certainty

`Starter Guardrail:`
- every new Contoso-adjacent case must name:
  - the missing interwoven pattern
  - why current Contoso plus synthetic stress was insufficient
  - what decision becomes safer once the case exists

## What We Should Not Do Yet

- do not treat raw remaining-function count as the main objective
- do not jump straight to a much broader enterprise package
- do not expand several fixture families at once
- do not let "cross-DLL evidence exists" stand in for "interwoven dependency
  is modeled and executable"
- do not treat synthetic stress as a substitute for runtime adoption

## What Is Missing Before Execution Prompts Are Fully Ready

This document is now strong enough to act as the main prompt, but a few
implementation-specific details should still be locked tranche by tranche:

- exact artifact names and schema fields for:
  - producer-consumer artifacts
  - shared-state artifacts
  - staged-chain artifacts
  - interwoven observer payloads
- exact Contoso seams to use first for each easy proof
- exact runtime/package surfaces that will prefer interwoven artifacts first
- compare/promotion implications once interwoven artifacts become
  decision-bearing
- retention and inspection rules for the added interwoven artifact family

These are not reasons to stop. They are the correct tranche-by-tranche
resolution points.

## Starter Defaults For The First Interwoven Implementation Tranches

These defaults are intentionally provisional.

They exist so the first interwoven prompts do not start from empty space.
They should be iterated from evidence as the tranche work produces stronger
local proofs.

### Canonical Starter Artifact Names

Use these as the first artifact family names unless a bounded implementation
tranche proves a better shape:

- `interwoven-producer-consumer-report.json`
- `interwoven-shared-state-report.json`
- `interwoven-staged-chain-report.json`
- `interwoven-observer-summary.json`
- `interwoven-contoso-proof-review.md`

If a campaign-owned variant is later needed, keep the same stem and add a
campaign-owned prefix or placement rather than inventing a new vocabulary.

### Starter Schema Fields

Use these as the first required fields.

#### Producer-Consumer Surface

- `artifact_type`
- `contract_version`
- `family`
- `producer_id`
- `producer_kind`
- `consumer_id`
- `consumer_kind`
- `state_tokens`
- `evidence_edges`
- `dependency_mode`
- `confidence`
- `contradiction_state`
- `observer_verdict`

#### Shared-State Surface

- `artifact_type`
- `contract_version`
- `carrier_id`
- `carrier_kind`
- `state_tokens`
- `downstream_consumers`
- `exporting_seams`
- `importing_seams`
- `staleness_risk`
- `confidence`
- `contradiction_state`
- `observer_verdict`

#### Staged-Chain Surface

- `artifact_type`
- `contract_version`
- `chain_id`
- `ordered_steps`
- `required_state_tokens`
- `producer_steps`
- `consumer_steps`
- `blocking_step`
- `confidence`
- `contradiction_state`
- `observer_verdict`

#### Interwoven Observer Summary

- `artifact_type`
- `contract_version`
- `subject_id`
- `subject_kind`
- `observer_name`
- `verdict`
- `reasons`
- `blocking_risks`
- `confidence`
- `contradiction_state`
- `canonical_sources`

### Starter Observer Payloads

The first interwoven observer family should include at least:

- `producer_consumer_plausibility`
- `shared_state_reuse_plausibility`
- `staged_chain_ordering_plausibility`
- `interwoven_slice_boundedness`
- `interwoven_state_staleness_risk`

Each payload should emit:

- `observer_name`
- `subject_id`
- `subject_kind`
- `verdict`
- `reasons`
- `blocking_risks`
- `confidence`
- `contradiction_state`
- `canonical_sources`

### First Contoso Seams To Use

The first easy-proof tranche should stay anchored to already familiar seams.

Start with:

- `contoso_config.dll`
  - producer of bootstrap/config state
- `contoso_reporting.dll`
  - consumer of upstream config/bootstrap state
- `contoso_pricing.dll`
  - consumer of config/bootstrap plus pricing-specific staged state
- `contoso_workflow.dll`
  - staged producer/consumer candidate for ordered interwoven chains
- `contoso_events.dll`
  - shared-state carrier candidate
- `contoso_cs_interwoven.dll`
  - explicit interwoven proving candidate for synthetic-plus-real seam mapping

The first easy proof should avoid broad package-wide claims and instead choose:

1. one producer -> one consumer
2. one producer -> several consumers
3. one shared-state carrier across two DLL families
4. one staged chain with explicit order

### First Runtime And Package Surfaces To Protect

When interwoven artifacts begin runtime adoption, prefer these surfaces first:

- decomposition-native slice planning inputs
- slice execution coordination inputs
- campaign truth interwoven summary fields
- campaign cohesion interwoven attribution fields

Do not start by pushing interwoven artifacts directly into compare or
promotion decisions.

### Starter Compare And Promotion Boundary

Until interwoven artifacts are runtime-proven and campaign-owned:

- treat them as architecture/debugging evidence first
- do not let them justify overlap or promotion claims by themselves

Promotion-safe usage should require all of:

- campaign-owned interwoven artifacts
- non-contradictory observer verdicts
- runtime attribution present
- no hidden collapse from staged chain to plain DLL grouping
- package-floor evidence class still meeting existing comparison law

### Starter Retention And Inspection Rules

Classify the first interwoven artifact family like this:

- canonical truth:
  - `interwoven-producer-consumer-report.json`
  - `interwoven-shared-state-report.json`
  - `interwoven-staged-chain-report.json`
- summary-only inspection:
  - `interwoven-observer-summary.json`
- tranche review / architecture note:
  - `interwoven-contoso-proof-review.md`

Do not let summary-only inspection become the only readable source of truth.
All summaries should point back to canonical artifacts.

### Starter Purpose Boundaries

These first interwoven artifacts should do only this:

- describe and verify interwoven relationships
- preserve bounded interwoven evidence
- help runtime decide what must stay live together

They should not yet:

- replace dependency classes
- replace initialization groups
- replace package-floor evidence class
- directly authorize promotion
- become a broad enterprise ontology

## High-Level Conclusion

Yes, this is the right methodology.

The repo should:

- keep current Contoso
- extract more generic methodology from it first
- add synthetic interwoven stress next
- expand Contoso only where methodology says the suite is still weak
- then move toward harder proving families and product transfer

This document is now the main place to drive that work and to record what each
interwoven tranche actually proved.

## Prompt 02 Review

- `What current Contoso proved:`
  - the starter producer-consumer, shared-state, and staged-chain artifact
    family is coherent enough to survive synthetic ambiguity without needing a
    second vocabulary
  - the current bounded reports can already carry:
    - competing producers
    - ambiguous shared state
    - overlapping chains
    - stale or forked state
    by making contradiction and observer verdicts explicit

- `What synthetic interwoven stress exposed:`
  - current Contoso does not naturally generate enough ambiguity to prove that
    conflicting producers or overlapping chains stay visible
  - synthetic pressure revealed the real pass/fail boundary for this layer:
    ambiguity is acceptable only when it stays contradiction-visible and
    boundedly reviewable
  - hidden ambiguity is now a first-class failure mode instead of a vague
    architecture concern

- `What changed in the generic model:`
  - the interwoven model now has a bounded synthetic stress surface in:
    - `api/pipeline/core/interwoven_stress_proof.py`
  - the first synthetic proof coverage now exists in:
    - `tests/test_interwoven_stress_proof.py`
  - Prompt 02 confirmed that the current interwoven artifact family does not
    need schema expansion yet to carry bounded ambiguity honestly

- `What must be added next to the suite:`
  - no new fixture family yet
  - the next bounded move is runtime and package adoption of the now
    stress-proven interwoven surfaces
  - Contoso expansion should still wait until runtime adoption proves which
    missing interwoven patterns remain truly underrepresented

- `What would count as failure if we ignore this now:`
  - if runtime adoption starts treating interwoven artifacts as trusted
    planning inputs without preserving the same contradiction visibility proven
    here
  - if a later reduced run consumes interwoven structures but hides competing
    producers or stale shared-state risks behind slice selection

- `What downstream phase would be poisoned by ignoring it:`
  - Prompt 03 would inherit interwoven artifacts that look contract-bearing but
    were never required to stay explicit under ambiguity
  - Prompt 04 would expand Contoso without knowing whether the real weakness
    was fixture coverage or runtime adoption

- `Did this reveal a weakness worth tightening in the weakness register?`
  - yes
  - the remaining weakness is now narrower again: synthetic ambiguity pressure
    exists, so the next unresolved seam is bounded runtime/package consumption
    of these interwoven surfaces

## Prompt 03 Review

- `What current Contoso proved:`
  - the decomposition-native planner and execution path can now consume
    bounded interwoven summaries without collapsing back into DLL-only
    explanation
  - campaign truth and cohesion can now project interwoven subject IDs,
    contradiction summaries, and attribution presence while keeping canonical
    interwoven artifacts session-owned

- `What synthetic interwoven stress exposed:`
  - the runtime boundary needed explicit related-DLL hints rather than implicit
    parsing of Contoso-shaped names
  - this confirmed the right generic shape for early adoption:
    interwoven artifacts remain canonical session truth, and runtime consumes a
    bounded projection layer instead of rewriting the artifact family

- `What changed in the generic model:`
  - the first bounded runtime/package adoption surface now exists in:
    - `api/pipeline/core/interwoven_runtime_projection.py`
  - interwoven summaries now flow into:
    - `api/pipeline/core/package_frontier_slice_planner.py`
    - `api/pipeline/core/slice_execution_coordinator.py`
    - `api/pipeline/core/decomposition_runtime_bridge.py`
    - `api/pipeline/runner.py`
    - `api/analysis/cohesion.py`
  - Prompt 03 held the intended boundary:
    - no compare/promotion change
    - no collector or ledger expansion
    - no live parallelism broadening

- `What must be added next to the suite:`
  - no broad new fixture family yet
  - the next bounded move is targeted Contoso expansion only for missing
    interwoven patterns that still are not represented after runtime adoption

- `What would count as failure if we ignore this now:`
  - if we expand Contoso before checking which interwoven patterns remain weak
    after runtime adoption
  - if a later run starts treating interwoven summaries as promotion-grade
    evidence without strengthening the comparison boundary first

- `What downstream phase would be poisoned by ignoring it:`
  - Prompt 04 would expand the suite without knowing whether the remaining gap
    is fixture coverage or still a runtime-consumption weakness
  - Prompt 05 would reason about product transfer from an interwoven system
    that was never actually exercised in runtime/package planning

- `Did this reveal a weakness worth tightening in the weakness register?`
  - yes
  - the remaining weakness is no longer proof-only interwoven handling; it is
    now deciding which missing interwoven patterns justify targeted Contoso
    expansion without drifting into blind suite growth

## Prompt 04 Review

- `What current Contoso proved:`
  - `contoso_cs_interwoven.dll` already contained a real producer-to-several-
    consumers fanout pattern around `CI_PrimeSession`
  - the suite was missing explicit metadata and tests for that pattern even
    though the fixture already existed

- `What synthetic interwoven stress exposed:`
  - synthetic stress can model ambiguity, but it cannot replace one real
    same-fixture fanout where a single producer feeds several consumers with
    different downstream argument shapes
  - this is exactly the kind of pattern that affects runtime planning
    confidence more than synthetic contradiction math alone

- `What changed in the generic model:`
  - the interwoven Contoso proving ground now explicitly records a real fanout
    pattern in:
    - `tests/fixtures/contoso_interwoven/truth_manifest.json`
  - targeted coverage now exists in:
    - `tests/test_interwoven_contoso_expansion.py`
  - Prompt 04 confirmed that the narrowest honest suite growth can be metadata
    and tests over an existing fixture rather than adding a new DLL family

- `What must be added next to the suite:`
  - no more Contoso growth in this tranche
  - the next move is transfer-oriented planning for harder proving families and
    product relevance

- `What would count as failure if we ignore this now:`
  - if we keep adding Contoso cases without proving that each one covers a
    distinct missing interwoven pattern
  - if we skip the transfer question and keep using Contoso growth as a proxy
    for product readiness

- `What downstream phase would be poisoned by ignoring it:`
  - Prompt 05 would overstate product transfer readiness without a clear view
    of what still remains Contoso-shaped

- `Did this reveal a weakness worth tightening in the weakness register?`
  - yes
  - the remaining weakness is no longer undisciplined Contoso growth inside the
    interwoven tranche; it is the transfer gap between a stronger Contoso
    proving ground and harder non-Contoso families

## Prompt 05 Review

- `What current Contoso proved:`
  - Contoso is now strong enough to support a first honest transfer review
    without pretending its execution assumptions are already portable

- `What synthetic interwoven stress exposed:`
  - synthetic stress proved the planning model is stronger than the execution
    adapter model, which is exactly why the next bounded move should be
    adapter-free first

- `What changed in the generic model:`
  - the first bounded beyond-Contoso transfer review now exists in:
    - `docs/architecture/engineScaling/engineScaling_Interwoven/INTERWOVEN-PRODUCT-TRANSFER-REVIEW.md`
  - the chosen harder proving family is now explicit:
    - transactional packages with staged handles, shared state, and fanout
  - the first product-facing pilot relevance is explicit:
    - a possible mainframe COBOL transaction package pilot

- `What must be added next to the suite:`
  - not another Contoso case
  - the next bounded move is one adapter-free transactional proving family
    that tests transfer without claiming runtime portability

- `What would count as failure if we ignore this now:`
  - if we treat the stronger interwoven architecture as proof that the current
    DLL execution path transfers directly to COBOL or other enterprise targets

- `What downstream phase would be poisoned by ignoring it:`
  - the next product-facing pilot discussion would overclaim runtime transfer
    instead of distinguishing generic planning from adapter-specific execution

- `Did this reveal a weakness worth tightening in the weakness register?`
  - yes
  - the remaining weakness is now the transfer and adapter gap itself, not a
    missing interwoven methodology inside Contoso
