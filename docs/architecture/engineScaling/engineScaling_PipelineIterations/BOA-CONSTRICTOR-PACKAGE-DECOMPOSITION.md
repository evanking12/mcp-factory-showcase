# Boa Constrictor Package Decomposition

## Why This Document Exists

When the engine eventually faces:

- 500 DLLs
- 10,000 functions
- interwoven cross-DLL dependencies
- cross-cutting initialization and state requirements

the problem is no longer "can one DLL pipeline work?"

The problem becomes:

- how does the system avoid choking on too much at once?
- how does it split the package into intellectually manageable work units?
- how does it preserve the smallest trustworthy truths and build upward?
- how does it prevent broad reruns from repaying already-solved work?

This document captures the intended direction:

- package intake before brute-force exploration
- frontier decomposition before broad execution
- cluster and initialization grouping before expensive reruns
- floor-to-ceiling iteration where each pass narrows the unknowns

The core idea is **BOA CONSTRICTOR**:

- do not try to swallow the entire package at once
- constrict the problem into smaller verifiable units
- preserve each trustworthy gain
- tighten around the true frontier only

---

## Plain-English Thesis

Right now, the engine still feels like:

- same core DLL pipeline
- smarter targeting
- rerun the hard 3 after freezing the easy 5

That is progress, but it is not yet the final scalable architecture.

The end goal is not:

- "run one DLL at a time forever"

The end goal is:

- ingest a package broadly and cheaply
- identify what is already understandable enough to freeze
- group the unknowns into meaningful dependency and state slices
- let the pipeline work those slices in a deliberate order
- carry each solved slice upward into package truth

That means the real future execution unit is not always:

- one DLL

It may instead be:

- one cluster inside one DLL
- one initialization group spanning several DLLs
- one dependency class cutting across a narrow DLL subset
- one package frontier slice that combines several related seams

The per-DLL pipeline remains important, but it becomes a worker inside a
larger decomposition system.

---

## The Boa Constrictor Rule

The architecture should always ask:

1. what is the smallest verifiable evidence we can trust?
2. what larger grouping can that evidence safely support?
3. what broader question can only be asked after that grouping is stable?

This means:

- small truth first
- then grouped truth
- then composed truth
- then package confirmation

Never reverse that order unless a broader run is the only honest way to answer
the question.

---

## What The Current Architecture Already Does Well

The project is not starting from zero. The current system already has:

- stage-based per-DLL exploration
- reusable truth gating
- cluster checkpoints
- prerequisite-state groups
- carryover observers
- package-floor control
- imported-lower-floor versus active-frontier distinction
- package frontier planning
- package-floor evidence classes

Those are real building blocks.

They prove that the engine can already:

- preserve some truth instead of repaying it
- restrict live work to a narrower frontier
- separate package rehearsal from package confirmation

That is a necessary precursor to the larger package-splitting architecture.

---

## What Is Still Missing

The architecture still lacks the front-end decomposition system required for
truly large packages.

The biggest missing pieces are:

- a broad but cheap package intake pass
- a generic frontier decomposition planner
- dependency-class grouping across many DLLs
- initialization-group hierarchy that can span multiple DLLs
- agent-facing work slices that are not just "this DLL"
- a scheduler that thinks in package frontier slices instead of mostly DLL jobs

This is why the system still feels like:

- same pipeline
- better reruns

That feeling is accurate.

The next architecture step is to turn it into:

- same trusted worker pipeline
- smarter package decomposition
- smarter slice scheduling

---

## The True End Goal

The real destination is:

1. individual findings
2. grouped into coherent local clusters
3. grouped again into prerequisite / initialization groups
4. grouped again into dependency classes and package frontier slices
5. composed into package truth
6. promoted only when comparison-safe

This hierarchy must be clear enough that:

- the engine can route work cheaply
- agents can consume the right slice without rebuilding the whole package
- package-scale iteration becomes controlled rather than rediscovery-heavy

That is the real product architecture.

---

## Organizational Layers The Pipeline Should Think In

The pipeline should eventually organize evidence and execution in these layers:

### 1. Finding Layer

This is the smallest unit:

- one function
- one observed call shape
- one working call
- one contradiction
- one artifact or state clue

Purpose:

- collect the smallest trustworthy evidence

Strength:

- highly precise

Weakness:

- too granular to plan large package work by itself

### 2. Cluster Layer

This groups functions that share:

- one state story
- one semantic purpose
- one handle family
- one output artifact family

Purpose:

- define the first meaningful unit of local progress

Strength:

- makes local reruns narrow and reusable

Weakness:

- clusters alone do not solve cross-DLL state propagation

### 3. Initialization / Prerequisite-State Layer

This groups functions and prerequisites that exist to make later work possible:

- sessions
- tickets
- handles
- bootstrap calls
- authorization/environment gates
- state tokens required across later consumer functions

Purpose:

- define the minimal state package required before consumers become meaningful

Strength:

- turns vague setup pain into explicit reusable packages of state

Weakness:

- easy to model too narrowly inside one DLL when the real group spans several
  DLLs

### 4. Dependency-Class Layer

This groups work by cross-DLL dependency shape, not by DLL ownership:

- shared entity continuity
- shared handle routing
- shared report/readback artifacts
- shared order / quote / transaction state
- shared environment / licensing state

Purpose:

- explain why separate DLLs must sometimes be planned together

Strength:

- gives the planner a generic way to reason about interwoven systems

Weakness:

- harder to infer automatically without strong intake and observer surfaces

### 5. Package Frontier Layer

This is the current unresolved slice of the package:

- what remains active
- what is already frozen
- what narrow groups must be executed now

Purpose:

- keep package runs cheap and honest

Strength:

- converts package work from rediscovery to targeted confirmation

Weakness:

- only works if the lower organizational layers are explicit and trustworthy

---

## What The First Run Should Do

For a huge package, the first run should **not** try to deeply solve all DLLs.

Its job is organizational.

### The First Run Should Establish

- package inventory
- DLL identity and rough role
- candidate dependency families
- candidate initialization groups
- candidate local clusters
- cheap environment and producer truth
- basic read-surface truth
- obvious frozen-versus-active frontier split
- early observer surfaces for later comparison

### The First Run Should Not Try To Do

- full deep exploration of every DLL
- package-wide final truth claims
- broad write unlock across the whole package
- full cross-DLL composition proof
- expensive confirmation work on unresolved high-risk seams

### First-Run Outputs The System Should Emit

- package inventory and package context
- candidate cluster map
- candidate initialization-group map
- candidate dependency-class map
- active frontier recommendation
- imported/cold-freezable truth recommendation
- first-package floor plan
- risk register for hidden-variable or capture concerns

### Why This Matters

If the first run tries to do too much:

- the engine pays too much too early
- hidden variables stay uncontrolled
- later reruns become noisy
- frontier planning remains reactive instead of deliberate

The first run is supposed to tell us:

- what kind of package this is
- where the likely pressure points are
- what not to spend on yet

It is an intake and decomposition run, not a hero run.

---

## What The Second Run Should Do

Once the first run has emitted package structure, the second run should become
the first truly strategic run.

### The Second Run Should Focus On

- imported lower-floor truth from run 1
- one or a few narrow package frontier slices
- explicit initialization-group replay where needed
- one or a few dependency classes that explain the active ceiling
- cluster-local or dependency-local proofs, not blanket package behavior

### The Second Run Should Answer

- were the proposed clusters real?
- were the proposed initialization groups real?
- which cross-DLL relationships were real versus accidental?
- what should now be frozen?
- what remains the true ceiling?

### The Second Run Should Upgrade

- guesses into reusable structure
- tentative groupings into trusted groupings
- initial package inventory into actionable package planning

This is where the architecture starts to feel like:

- a decomposition system

instead of:

- a DLL runner with better bookkeeping

---

## What Later Runs Should Do

After the first and second runs, later runs should become increasingly narrow
and intentional.

Each later run should do one of these:

- confirm a now-trusted initialization group
- confirm a dependency class
- clear one active package frontier slice
- repair a contradiction in preserved truth
- verify that a previously active slice can now be frozen

This means later runs should get:

- narrower
- cheaper
- more attributable

not broader.

---

## How Cross-Weaving Initialization States Should Be Modeled

This is one of the most important scaling questions.

Initialization state is not just:

- "setup functions in one DLL"

Often it is:

- a multi-step state package
- created across several functions
- sometimes across several DLLs
- required by a later consumer group elsewhere

### Cross-Weaving Initialization State Means

- a config DLL may issue a ticket used by a reporting DLL
- a workflow DLL may produce a handle required by pricing
- a gateway DLL may establish a session that many later clusters depend on

So initialization cannot remain:

- one global init bucket
- or one purely local DLL concern

It needs to become:

- hierarchical
- adjacent to clusters
- explicit about exports and consumers

### The Right Model

Each initialization group should declare:

- purpose
- member functions
- produced state artifacts
- exported handles/tickets/tokens
- downstream dependent clusters
- downstream dependent DLL slices
- observer contracts
- latest trusted proof
- known failure modes

### Why This Matters

Without this model:

- the engine rediscovers setup repeatedly
- package truth becomes fragile
- agents cannot see why a hard function is failing
- cross-DLL work stays opaque and expensive

Initialization groups are one of the main ways we turn "too much food" into
"structured meals."

---

## The Package Intake / Frontier Decomposition System

This is the next major architecture layer that should exist above the current
pipeline.

### Purpose

Take a large package and answer:

- what do we already know?
- what do we tentatively know?
- what is likely related?
- what must be kept apart?
- what should be frozen?
- what should stay live?

### Inputs

- package inventory
- discovery metadata
- low-cost stage results
- prior package truth
- prior cluster results
- prior initialization-group truth
- dependency overlap signals
- baseline contract if one exists

### Outputs

- imported lower-floor truth set
- active frontier set
- candidate cluster groups
- candidate initialization groups
- candidate dependency classes
- high-risk interwoven groups
- recommended execution order
- stop conditions for broad runs

### Why It Is Product-Critical

This is the system that makes the architecture enterprise-usable.

Without it, the engine remains:

- strong locally
- expensive globally

With it, the engine becomes:

- capable of handling large packages through deliberate decomposition

---

## What Agents Need To See

If multiple strong coding/reasoning agents are going to help, they must not be
fed:

- one giant package blob

They need bounded, explicit work surfaces.

The system should eventually be able to show each agent:

- current package floor
- current active frontier slice
- related clusters
- required initialization groups
- dependency class
- imported lower-floor truth
- preserved evidence artifacts
- stop conditions
- observer expectations

That way the agents are not guessing:

- what matters
- what is already trusted
- what they are allowed to touch

This is why the organization of findings, clusters, and initialization groups
is not just nice-to-have. It is essential for intelligent agent use.

---

## Strengths Of The Direction We Are Heading

### Strength 1: It preserves economics

The architecture is moving toward spending on:

- the active frontier only

instead of:

- the whole package every time

### Strength 2: It improves trust

By preserving lower-floor truth explicitly, the system can better explain:

- what was imported
- what was rerun
- what regressed
- where the first broken handoff was

### Strength 3: It supports productization

A package intake and decomposition system is generic enough to move beyond the
fixture suite into enterprise packages.

### Strength 4: It supports agent collaboration

Once work is grouped correctly, multiple strong agents can help on:

- triage
- classification
- carryover auditing
- cluster-local fixes

without the main executor losing coherence.

---

## Weaknesses And Gotchas

### Weakness 1: We still think too much in DLLs

The architecture is better than before, but the default mental model is still:

- DLL job first

That is not enough for truly interwoven packages.

### Weakness 2: Initialization grouping is still early

We have prerequisite-state groups, but not yet a mature hierarchy of
cross-weaving initialization packages across many DLLs.

### Weakness 3: Intake is not yet a first-class system

We do not yet have a broad package intake pass whose main purpose is
decomposition rather than discovery.

### Weakness 4: It is easy to overfit to the fixture suite

The current proof ground is still Contoso-shaped.
That is acceptable now, but dangerous if the planner and grouping systems start
assuming fixture-specific shapes instead of generic package behavior.

### Gotcha 1: Broad first runs feel productive but are often wasteful

A broad first run can create the illusion of progress while actually producing:

- too much noisy evidence
- too little organized structure

### Gotcha 2: Cross-DLL overlap is not the same as dependency truth

Two DLLs may share tokens or entities without being part of the same active
execution slice.

The planner must distinguish:

- overlap
- true dependency
- true initialization coupling

### Gotcha 3: Reduced frontier confirmation is not package-wide confirmation

A reduced frontier run can be valid and comparison-safe without implying that
the whole package is ready for blanket conclusions.

### Gotcha 4: Agents can amplify confusion if slices are weak

Multiple strong agents do not solve weak decomposition.
If the slice definitions are poor, they will only produce more parallel noise.

---

## Product Adjacencies

To make this a real product and not just a strong research pipeline, the system
must eventually support:

### 1. Package Intake UI / Artifact Layer

Humans and agents need a readable surface for:

- package inventory
- frontier groups
- initialization groups
- dependency classes
- imported truth
- active ceiling

### 2. Stable Group Identifiers

Clusters, initialization groups, and dependency classes need persistent IDs so
later runs can reuse and compare them.

### 3. Package-Generic Planner Interfaces

The planner should not be Batch-B-shaped. It should accept:

- package summaries
- prior campaign truth
- baseline contracts
- overlap and dependency evidence

### 4. Observer-Driven Scheduling

The scheduler should make choices from observer outputs rather than human
intuition alone.

### 5. Explicit Evidence Stores

Specificity should live in:

- evidence artifacts
- planner outputs
- observer surfaces

not in hardcoded enterprise assumptions inside core logic.

---

## What The Architecture Should Ask At Large Scale

For a 500-DLL package, the first questions should be:

- what are the likely families here?
- what are the likely shared states?
- what are the likely shared handles or entity flows?
- what can be read cheaply?
- what seems dangerous or write-gated?
- what should stay frozen until later?

Not:

- how do we deeply solve every DLL immediately?

And by the second run, the questions should become:

- which groupings proved real?
- which initialization states were actually shared?
- which frontier slice gives the best learning value?
- what can now be imported instead of rerun?

That is the correct large-scale mindset.

---

## The Intended Long-Term Run Shape

The architecture should mature toward this run pattern:

### Run 1

- broad package intake
- cheap discovery
- initial grouping
- initial frozen-versus-active split

### Run 2

- prove the best candidate frontier slices
- prove initialization groups
- prove dependency classes
- promote trustworthy lower-floor truth

### Run 3+

- keep only the true active ceiling live
- run narrow package frontier slices
- preserve solved work aggressively
- expand only when a higher-level confirmation question remains

This is the boa constrictor shape:

- broad intake
- tighter grouping
- tighter frontier
- tighter confirmation

---

## Short Version

The current architecture is moving in the right direction, but it is not yet
the final large-package system.

What exists now:

- a strong per-DLL worker pipeline
- floor-to-ceiling preservation and package control

What must come next:

- package intake
- frontier decomposition
- hierarchical initialization grouping
- dependency-class planning
- agent-facing execution slices

The final goal is not:

- "same pipeline, rerun fewer DLLs"

It is:

- "organize a huge package into the smallest trustworthy work units, preserve
  each solved unit, and only spend live runtime on the real unresolved
  frontier"

That is the boa constrictor architecture.

---

## Cross-DLL Dependency Detection Should Be Above The DLL Pipeline

One of the clearest architectural questions is:

- should the pipeline gain a whole new stage whose job is to determine whether
  DLLs depend on each other?

The answer is:

- yes, the system needs that capability
- no, it should not just be bolted on as another DLL-local stage inside
  `S-00` through `S-07`

The current per-DLL worker pipeline is already strong at doing local heavy
lifting once the target is chosen.

The missing capability is not:

- "make one DLL pipeline smarter in isolation"

It is:

- "determine what the real work units are before deep execution begins"

So cross-DLL dependency detection should live as a new:

- package-level intake
- dependency-decomposition
- frontier-planning layer

above the per-DLL pipeline.

That layer should answer:

- which DLLs are likely isolated
- which DLLs share initialization state
- which DLLs are likely consumers of other DLLs' outputs
- which DLLs belong to the same dependency class
- which DLL groups should be explored together
- which DLLs or slices should be frozen or deferred

This is not merely a convenience.

It is the first serious answer to the question:

- how do we avoid letting a 500-DLL package collapse into chaos?

---

## The Complexity Model Should Stay Cheap And Broad

This package-intake dependency layer should be:

- broad
- cheap
- graph-oriented
- minimally invasive

It does not need to deeply solve behavior.

It needs to detect and propose structure.

The right mental model is:

- an `O(n)` style inventory over DLLs
- plus graph-building over candidate dependency relationships

In practice this is closer to:

- `O(n + m)`

where:

- `n` = DLL count
- `m` = inferred dependency edges

That is acceptable.

The point is not to avoid all cost.
The point is to avoid spending deep behavioral cost before the system even
knows how the package should be split.

---

## Floor-To-Ceiling Should Become Continuous, Not Small-Capped

The current bounded cycle counts are safety rails, not the final design.

The long-term behavior should be:

- keep iterating while the frontier shrinks
- keep iterating while failure localizes
- keep iterating while truth becomes more trustworthy
- stop only when:
  - the frontier is empty
  - there is no meaningful progress
  - contradictions increase
  - broader redesign is required

That is the true boa constrictor behavior.

It should not mean:

- three iterations
- five iterations
- arbitrary small caps as the architecture itself

It should mean:

- keep constricting until the package is actually consumed in an organized way

The bounded cycle counts are still useful as:

- development safeguards
- unattended-operation safety bounds
- anti-wheel-spinning rules

But they are not the intended product behavior.

---

## Sharded Cheap Intake Is The Strongest Next Crackable Layer

For a very large package, a strong next-step architecture is:

- split the package into many cheap intake shards
- let those shards collect broad, low-cost evidence
- merge that evidence into better organizational groupings
- then choose which slices deserve expensive exploration

Example shape:

- `500 DLLs`
- split into `50` cheap intake runs of `10 DLLs` each
- merge the `50` intake results
- infer:
  - candidate clusters
  - candidate initialization groups
  - candidate dependency classes
  - initial imported versus active frontier split
- only then launch deeper work where justified

This is likely the strongest crackable architectural layer because it directly
attacks the problem of:

- too much food on the plate

without pretending we can deeply process the whole package at once.

---

## Important Refinement: Do Not Start With 50 Full Deep Runs

The strong version of the idea is not:

- `50` full expensive pipeline runs immediately

It is:

- `50` cheap intake passes

Then:

1. merge shard evidence
2. derive dependency and state groupings
3. identify the first trustworthy frontier slices
4. run the expensive worker pipeline only on those slices
5. merge and tighten upward
6. repeat

If we start with `50` full deep runs too early, we risk:

- paying too much too soon
- splitting true cross-DLL relationships across arbitrary shard boundaries
- generating too much noisy evidence before structure exists

So the right version of the idea is:

- parallel intake first
- deep execution second

---

## What The First-Floor Parallel Passes Should Do

The first-floor sharded passes should be organizational, not heroic.

Each cheap shard should try to establish:

- package-local DLL identity
- likely family membership
- rough dependency clues
- rough initialization clues
- obvious producer and consumer patterns
- obvious read-safe surfaces
- obvious environment or session gates
- likely cluster candidates

Each cheap shard should avoid:

- deep full unlock work across all functions
- final package truth claims
- expensive broad write behavior confirmation
- premature package-wide composition claims

These passes are supposed to answer:

- what are we looking at?
- what likely belongs together?
- what should not be paid for deeply yet?

That is how the engine starts to build an organizational hierarchy before it
earns the right to ask harder questions.

---

## How The Shards Should Merge Upward

After the cheap shard passes, the system should merge upward into:

### Candidate Cluster Groups

- functions and DLL-local surfaces that appear to share one state story or
  semantic goal

### Candidate Initialization Groups

- sessions
- tickets
- handles
- auth state
- bootstrap flows
- prerequisite environmental state

### Candidate Dependency Classes

- shared entity continuity
- shared handles
- shared report/readback artifacts
- shared transaction/order/quote flows
- shared licensing/environment dependencies

### Candidate Imported Truth

- DLLs or slices that look easy, stable, or already sufficiently proven

### Candidate Active Frontier

- DLLs or slices that still look expensive, ambiguous, or interwoven

This merge step is where the architecture starts to turn:

- many cheap observations

into:

- a plan for expensive work

---

## Cross-Weaving Initialization States Become Central Here

In this sharded model, cross-weaving initialization state becomes even more
important.

A large package will often contain states that are:

- created in one shard
- consumed in another shard
- partially understood in both

That means shard results cannot just be merged as flat DLL summaries.

They must also contribute to:

- initialization-group inference
- initialization-group expansion
- downstream consumer mapping

The architecture should be able to say:

- this shard found the ticket/session bootstrap
- this other shard found likely downstream consumers
- these should be merged into one initialization group

Without that, the sharded passes become fragmented and lose much of their
value.

---

## The Package Intake / Dependency-Decomposition Layer Should Output Agent-Facing Slices

This future layer should not just output a human summary.
It should output machine-usable slices for the executor and for side agents.

Each slice should be able to say:

- owning floor
- candidate dependency class
- candidate initialization groups
- candidate clusters
- imported lower-floor truth
- active unresolved frontier
- recommended next execution order
- observers that must pass before promotion
- stop conditions

That would let agents work on:

- one slice

instead of:

- one giant package blob

This is a major product-quality requirement, not just a convenience.

---

## Why This Matters For The Product

At product scale, the engine cannot depend on:

- manual human intuition to split giant packages
- repeated broad reruns until structure emerges

The product needs to be able to do this itself:

1. take in a package too large to understand deeply at once
2. split it cheaply
3. merge the cheap results into structure
4. pick the first expensive frontier wisely
5. keep narrowing until the hard questions are isolated

That is the product form of the boa constrictor idea.

It is not enough that the engine can:

- eventually solve hard local problems

It must also know:

- how to approach too much complexity without wasting money and time

---

## Updated Short Version

The architecture is heading in the right direction, but the missing layer is
now clearer.

What we already have:

- a strong per-DLL worker pipeline
- floor-to-ceiling preservation and frontier control

What must come next:

- package-level cross-DLL dependency detection
- cheap sharded intake passes
- shard merge into cluster / initialization / dependency groupings
- agent-facing frontier slices
- continuous boa-constrictor iteration until the real frontier is exhausted

The future should not feel like:

- same pipeline, rerun fewer DLLs

It should feel like:

- broad intake
- deliberate grouping
- narrow expensive execution
- repeated tightening
- preservation of every trustworthy gain

That is how the system becomes able to handle packages that are far larger
than anything in the current fixture suite.

---

## What Must Be Added Before Full Implementation

The boa-constrictor direction is now strong enough to implement, but only if
we add the missing rails that keep the new systems governable.

The major missing rails are:

- identity and lifecycle rules
- run economics and parallel-width rules
- observer contracts for the new decomposition systems
- contradiction handling for shard merge and slice planning
- retention and compression policy for the new artifact volume

Without those rails, the architecture is directionally correct but still too
soft for a safe large implementation tranche.

### Identity And Lifecycle Rules

Every new decomposition object needs a stable lifecycle:

- intake shard
- merged cluster candidate
- initialization-group candidate
- dependency-class candidate
- package frontier slice

Each of these needs:

- stable ID
- source lineage
- supersedes rule
- contradiction state
- closure or retirement state

Why:

- without lifecycle rules, later runs cannot compare, supersede, or reuse
  structure coherently

Strength:

- enables comparison, merge stability, and agent assignment

Weakness if missing:

- label drift
- duplicate structures
- merge ambiguity that never settles

### Run Economics And Parallel-Width Rules

We now say "cheap shard passes" and "parallel intake", but that must be made
concrete.

We need explicit policy for:

- target DLL count per shard
- max shard runtime budget
- max shard token/tool budget
- when a shard is too expensive to remain an intake pass
- when to split shard width further
- when to merge shard width upward
- what can actually run in parallel given the bridge/API constraints

Why:

- if the economics are vague, the intake layer can silently become as
  expensive as the work it was meant to prevent

Strength:

- makes "cheap first passes" a measurable architectural promise

Weakness if missing:

- broad but costly shard runs
- accidental deep work
- false confidence that package intake is cheap when it is not

### Observer Contracts For New Systems

The new systems should not rely on human interpretation alone.
They need explicit expected-versus-observed observers.

We need observers for:

- shard validity
- shard structure sufficiency
- merge coherence
- initialization-group plausibility
- dependency-class plausibility
- frontier-slice boundedness
- imported-truth preservation

Why:

- we already know from the rest of the repo that expensive work must be gated
  by machine-readable contract surfaces

Strength:

- keeps decomposition systems aligned with existing stage and package-floor
  governance

Weakness if missing:

- decomposition becomes prompt-memory and judgment-heavy again

### Contradiction Handling For Merge

Shard merge and dependency planning will generate contradictions by default.
That is expected.

The system needs explicit contradiction states such as:

- tentative
- blocked
- contradicted
- quarantined
- superseded
- confirmed

Why:

- otherwise the system either overclaims too early or hides ambiguity

Strength:

- ambiguity stays visible and actionable

Weakness if missing:

- false certainty
- poisoned frontier planning

### Artifact Retention And Compression Policy

The intake layer can easily create too many artifacts.

We need rules for:

- canonical shard artifacts
- summary versus detail artifacts
- retention of raw versus merged structures
- dashboard-style inspection outputs

Why:

- at 500 DLL scale, unbounded artifact growth becomes its own failure mode

Strength:

- keeps humans and analysis agents able to review the system

Weakness if missing:

- observability becomes technically complete but practically unusable

### Provisional Defaults For Phase 0

These are not final forever.
They are first implementation defaults that are good enough to begin safely.

#### Identity Format Defaults

Use stable prefixed IDs:

- shard: `shard::<package_id>::<graph_epoch>::<ordinal>`
- candidate cluster: `cluster_candidate::<package_id>::<stable_hash>`
- candidate initialization group: `init_group_candidate::<package_id>::<stable_hash>`
- candidate dependency class: `dependency_class::<package_id>::<stable_hash>`
- frontier slice: `frontier_slice::<package_id>::<graph_epoch>::<ordinal>`

Why:

- readable by humans
- deterministic enough for merge and comparison
- easy to supersede without losing lineage

#### Contradiction-State Enum Default

Use this initial contradiction state set:

- `none`
- `tentative`
- `blocked`
- `contradicted`
- `quarantined`
- `superseded`
- `confirmed`

Why:

- enough range to preserve ambiguity without overcomplicating the first pass

#### Supersedes / Closure Defaults

Every decomposition object should support:

- `supersedes_id`
- `supersedes_reason`
- `closed_at`
- `closure_reason`
- `active`

Default closure reasons:

- `merged_forward`
- `replaced_by_higher_confidence`
- `invalidated_by_contradiction`
- `retired_as_noise`
- `promoted_to_verified_structure`

Why:

- gives merge and reuse a stable lifecycle language immediately

#### Shard Economics Defaults

First enforceable defaults for a cheap shard pass:

- target shard width: `10 DLLs`
- max shard width before forced split: `15 DLLs`
- target shard live runtime budget: `12 minutes`
- hard shard runtime ceiling: `20 minutes`
- target shard tool/token intensity: `intake_only`
- max expensive follow-up inside shard: `0`

Why:

- these are conservative enough to keep intake distinct from deep execution
- they can be tuned later from evidence

#### Parallel Width Defaults

Initial planning default:

- allow parallel shard planning conceptually
- keep live execution serialized until lane isolation is upgraded
- use shard parallelism first for:
  - static inventory
  - artifact digestion
  - merge analysis

Why:

- this respects the current repo execution constraints while still shaping the
  future architecture correctly

#### Observer Payload Defaults

Initial shard-validity observer should emit:

- `observer_name`
- `object_id`
- `status`
- `runtime_budget_ok`
- `required_artifacts_present`
- `hidden_variable_state_recorded`
- `capture_valid`
- `reasons`
- `warnings`

Initial merge-coherence observer should emit:

- `observer_name`
- `object_id`
- `status`
- `provenance_complete`
- `stable_identity_present`
- `contradictions_visible`
- `ambiguity_score`
- `warnings`

Initial frontier-slice boundedness observer should emit:

- `observer_name`
- `object_id`
- `status`
- `imported_truth_explicit`
- `active_work_explicit`
- `slice_width`
- `dll_count`
- `cluster_count`
- `init_group_count`
- `reopened_imported_truth`
- `warnings`

Why:

- these payloads are small, legible, and sufficient for a first implementation

#### Retention Policy Defaults

Default retention split:

- canonical:
  - shard identity
  - shard summary
  - candidate cluster artifacts
  - candidate init-group artifacts
  - candidate dependency-class artifacts
  - frontier slice artifacts
  - observer summaries
- summary-only:
  - raw shard note aggregations
  - intermediate merge traces
  - temporary scoring breakdowns
- superseded or compacted:
  - prior candidate versions with a `supersedes_id`
  - redundant merge attempts
  - detail traces already represented in canonical summaries

Why:

- keeps the system inspectable without losing important lineage

---

## Cohesive Implementation Order

Yes, this must be built in a strict order from easiest to verify upward.

The right order is:

### Phase 0: Rails Before Scale

Build first:

- identity and lifecycle rules
- run economics and width rules
- observer vocabulary
- contradiction states
- artifact retention rules

Why first:

- these are cheap to define
- they become the rails all later systems use

What this phase should verify:

- schema normalization
- backward-tolerant readers
- explicit state transitions for new objects

### Phase 1: Cheapest Structural Intake

Build next:

- Package Intake Shard Runner
- Shard Inventory And Observation Emitter

Why next:

- they are the broadest and cheapest systems
- they create raw structure without needing a full merge or scheduler yet

What this phase should verify:

- shard validity
- shard runtime economics
- emitted artifact quality
- provenance preservation

### Phase 2: Merge Without Overclaiming

Build next:

- Shard Merge Coordinator

Why next:

- merge should only happen after shard outputs are stable enough to merge

What this phase should verify:

- merge provenance
- ambiguity retention
- contradiction handling
- stable IDs across reruns

### Phase 3: Real Cross-DLL Structure

Build next:

- Cross-DLL Initialization-Group Inference
- Dependency-Class Inference

Why next:

- this is where the architecture stops being mostly DLL-shaped

What this phase should verify:

- actual cross-DLL group formation
- distinction between overlap and true dependency
- reusable initialization-state export/import reasoning

### Phase 4: Package Spending Policy

Build next:

- Package Frontier Slice Planner

Why next:

- this is the first system that directly decides what expensive work should run

What this phase should verify:

- imported-to-active split
- slice boundedness
- slice rationale
- package-floor compatibility

### Phase 5: Execution Mapping

Build next:

- Slice Execution Coordinator

Why next:

- only after slices are meaningful should they be turned into execution units

What this phase should verify:

- protected imported truth
- bounded slice execution
- correct mapping into runner/runtime

### Phase 6: Inspection And Agent Usability

Build next:

- Decomposition Observability And Inspection Surface

Why last:

- this layer should summarize real working systems, not speculate ahead of
  them

What this phase should verify:

- bounded human readability
- bounded analysis-agent readability
- ambiguity visibility
- useful summaries without artifact sprawl

---

## The Current Weaknesses To Be Concerned With

If implementation started immediately, the biggest concerns would be:

### Concern 1: The decomposition layer still lacks explicit observer law

We already solved this problem for stages and package-floor work.
We have not yet solved it for shards, merges, and dependency classes.

### Concern 2: The economics are not yet enforced

The docs say "cheap shard passes", but the repo does not yet make that a hard
runtime or budget boundary.

### Concern 3: The scheduler still thinks too much in DLL jobs

The current engine can preserve and narrow, but it does not yet fully think in
package slices.

### Concern 4: Cross-DLL modeling is still stronger at attribution than at
first-class planning

We can often explain cross-DLL effects after the fact better than we can use
them to plan the first split.

### Concern 5: We can still drown ourselves in artifacts

Without a retention and summarization policy, the new architecture will create
more insight and more clutter at the same time.

### Concern 6: The fixture suite is still the proving bound

That is acceptable for the next tranche, but the shard and merge systems must
remain generic enough that they can later move beyond Contoso-shaped packages.

### Concern 7: The decomposition systems are specified, but the shared rails are not yet implemented

The architecture now says the right things, but the common rails still do not
exist in code.

Why this matters:

- this is the main point where a strong design can still crumble during
  implementation

### Concern 8: “Cheap shard pass” is still an idea, not yet an enforced contract

We still need the runtime and budget law that makes intake truly cheap.

Why this matters:

- if we do not enforce cheapness, the intake layer can silently become a broad
  expensive rerun layer

### Concern 9: The scheduler still thinks more in DLL jobs than in frontier slices

The runner can preserve and narrow, but it does not yet naturally think in the
same slice units the new architecture requires.

Why this matters:

- slice planning can be correct on paper but still map back into DLL-shaped
  execution behavior

### Concern 10: Cross-DLL planning is still weaker than cross-DLL attribution

We are better at explaining cross-DLL relationships after the fact than at
using them to split the package correctly at the start.

Why this matters:

- the boa-constrictor architecture depends on first splits that are at least
  directionally right

### Concern 11: Artifact volume can outrun reviewability

The more successful the intake and merge systems become, the more artifacts
they will produce.

Why this matters:

- if retention and compression are not implemented early, humans and agents
  will lose the ability to inspect the system coherently

---

## Immediate Concern And Implementation Rule

The immediate concern is no longer lack of vision.
It is implementing the systems in a governable order.

That means:

- do not jump straight into shard merge, dependency classes, and slice
  scheduling all at once

The correct next move is:

- build Phase 0 first:
  - lifecycle schema
  - economics schema
  - observer vocabulary
  - contradiction states
  - artifact retention policy

Why:

- this is the easiest layer to verify
- it creates the rails every later system needs
- it reduces the chance that the decomposition layer will collapse into
  ungoverned complexity

---

## Implementation Discipline For Each System

When these systems start getting implemented, the repo should not try to settle
every later-stage detail in advance.

Instead, each system should resolve its remaining specifics dynamically,
system by system.

That includes:

- exact repo file and module ownership
- final canonical JSON schemas
- exact test fixture design
- exact merge algorithms
- exact confidence and ambiguity scoring
- exact scheduler behavior once slices become executable
- exact compare and promotion implications when shard-derived structures are
  reused across many runs

This should happen in order, per system, because:

- trying to finalize all of it at once would force speculative architecture
- the earlier systems will teach us what the later systems actually need

### What Each System Prompt Should Force Us To Answer

For each system, implementation should explicitly answer:

- what does this system do right now?
- what does it not do yet?
- what exact purpose is it serving?
- what outputs does it emit?
- what observer verifies it?
- what downstream systems are allowed to trust from it?
- what evidence would justify expanding or narrowing its role later?

### Why This Matters

System purpose may evolve, but it should evolve through:

- evidence
- contract updates
- verified behavior

not through:

- ad hoc drift
- implicit prompt memory
- vague overlap with neighboring systems

That is how we keep the decomposition layer cohesive while still allowing it to
learn from implementation.

---

## The Current Adjacent Systems We Should Reuse

Before inventing new decomposition systems, we should ask:

- what verification, collection, and contract surfaces already exist that can
  anchor good design?

Right now we already have strong adjacent systems in play.

### Contract And Stage Registry

Primary surfaces:

- `api/pipeline/core/handoff_contract.py`
- `api/pipeline/core/finding_status.py`
- `api/pipeline/core/compatibility.py`

What they already give us:

- canonical stage identities
- canonical transition expectations
- canonical artifact requirements
- optional skip semantics
- status normalization
- backward-tolerant compatibility discipline

Why they matter here:

- package intake shards should not invent ad hoc artifact semantics
- shard outputs should be contract-bearing from day one
- decomposition systems should plug into the same evidence and compatibility
  discipline as the rest of the pipeline

### Collection And Strict Audit

Primary surface:

- `scripts/harness_lib/collector.py`

What it already gives us:

- session collection
- strict artifact auditing
- stage-index and transition-index checks
- validity decisions
- artifact inventory
- ledger row emission

Why it matters here:

- shard intake runs need to become auditable first-class runs
- a shard should be able to say "this intake run is valid" or "this shard is
  not trustworthy" using the same collection discipline
- this prevents package intake from becoming a second-class, undocumented side
  path

### Floor-To-Ceiling Runtime And Package Truth

Primary surfaces:

- `api/pipeline/core/floor_iteration.py`
- `api/pipeline/core/package_frontier_planner.py`
- `api/pipeline/runner.py`
- `api/analysis/cohesion.py`

What they already give us:

- floor vocabulary
- package floor evidence classes
- imported-lower-floor versus active-frontier distinction
- campaign truth
- campaign cohesion
- campaign attribution

Why they matter here:

- shard merge outputs should eventually become inputs to package-floor planning
- decomposition should not live outside the existing floor vocabulary
- package intake should feed the package frontier planner rather than bypass it

### Cluster And Prerequisite-State Structures

Primary surfaces:

- `api/pipeline/core/cluster_checkpoint.py`
- `api/pipeline/core/prerequisite_state_groups.py`

What they already give us:

- cluster identity
- adjacent prerequisite-state relationships
- machine-readable local grouping concepts

Why they matter here:

- shard merge should not invent a second local grouping language
- it should extend cluster and prerequisite-state concepts upward into package
  intake and dependency planning

### Campaign And Comparison Surfaces

Primary surfaces:

- `sessions/ledger/run_ledger.jsonl`
- `codex/tasks/compare-runs.md`
- `.agents/skills/baseline-promoter/SKILL.md`
- `AGENTS.md`

What they already give us:

- comparable-profile discipline
- overlap-claim discipline
- package-floor evidence boundaries
- promotion safety rules

Why they matter here:

- shard systems need to produce data that can later support safe comparisons
- package intake should not produce groupings that cannot be tracked or
  compared later

### Human-Readable Architecture Surfaces

Primary surfaces:

- `api/pipeline/core/FULL_FLOW.md`
- `docs/architecture/charts/01-engineering-overview-4/`
- `docs/architecture/engineScaling/`

What they already give us:

- a canonical explanation layer
- chart conventions
- scaling doctrine

Why they matter here:

- if shard intake and package decomposition become important enough to govern
  expensive campaigns, they need to exist here too, not only in prompt memory

---

## What Each Intake Shard Must Emit

If we introduce cheap shard passes, each shard must leave behind reusable
structure. Otherwise the system is just generating more traces.

Each intake shard should emit at least these artifact classes:

### 1. Shard Identity Artifact

Contains:

- shard ID
- package ID
- participating DLLs
- graph epoch
- intake profile
- campaign lineage

Why:

- without stable shard identity, later merge and comparison become fragile

### 2. Shard Inventory Artifact

Contains:

- DLL inventory for the shard
- rough DLL roles
- rough DLL family guesses
- obvious producer versus consumer guesses

Why:

- this is the base package intake layer

### 3. Candidate Cluster Artifact

Contains:

- candidate local clusters
- member functions
- cluster rationale
- confidence
- source evidence

Why:

- cluster hypotheses need to become explicit before we can test them

### 4. Candidate Initialization-Group Artifact

Contains:

- candidate prerequisite-state groups
- exported handles/tokens/tickets/sessions
- likely downstream consumers
- confidence
- source evidence

Why:

- this is the main way shard passes start to expose cross-weaving state

### 5. Candidate Dependency-Class Artifact

Contains:

- likely cross-DLL dependency classes
- participating DLLs
- participating clusters or functions
- edge confidence
- observed shared artifacts or entities

Why:

- this is how we avoid treating cross-DLL complexity as mystery overlap

### 6. Shard Frontier Recommendation Artifact

Contains:

- recommended imported lower-floor truth
- recommended active frontier items
- recommended defer set
- recommended next execution order

Why:

- cheap intake should end by shaping later expensive work

### 7. Shard Observer Summary

Contains:

- run validity
- hidden-variable warnings
- capture warnings
- comparison safety warnings
- confidence summary

Why:

- not every shard should be trusted equally

---

## Merge Rules For Shard Results

Shard merge should be a real system, not an ad hoc manual synthesis step.

The merge rules should follow these principles:

### Rule 1: Prefer evidence-backed unions over arbitrary unions

Do not merge shards just because:

- they were adjacent in input order
- they happened to run together

Merge them when evidence suggests:

- shared initialization state
- shared dependency classes
- shared artifact families
- shared entity continuity

### Rule 2: Preserve ambiguity instead of forcing early certainty

If two shards suggest a possible shared initialization group but confidence is
still weak, the merge layer should output:

- tentative grouping

not:

- false certainty

### Rule 3: Merge by stable IDs, not by loose labels

Where possible, merge should rely on:

- DLL identity
- cluster ID
- group ID
- package ID
- graph epoch

not on brittle text-only labels.

### Rule 4: Carry provenance into every merged object

Every merged cluster, initialization group, or dependency class should retain:

- source shards
- source evidence
- merge confidence
- unresolved contradictions

This is essential for trust.

### Rule 5: Let merge produce both imported truth and active frontier

Merge is not only about unifying evidence.
It is also about deciding:

- what is safe to freeze
- what must remain active

### Rule 6: Do Not Collapse Cross-Weaving State Into One Giant Bucket

Initialization groups must stay bounded even when they are cross-DLL.

The merge layer should create:

- multiple explicit state groups

not:

- one giant package init bucket

---

## Clear Boundary Definitions

One of the major remaining weaknesses is that these concepts can blur together.
They need explicit boundaries.

### Cluster

A cluster is:

- a coherent local seam
- usually dominated by one state story or semantic purpose
- primarily a local progress unit

A cluster is not:

- a whole package-wide dependency class
- a whole initialization hierarchy

### Initialization Group

An initialization group is:

- the bounded prerequisite-state package required before one or more consumer
  clusters become meaningful

It may be:

- within one DLL
- across several DLLs

An initialization group is not:

- just any early function
- just any cluster

### Dependency Class

A dependency class is:

- a cross-DLL relationship category
- a reusable explanation of why separate surfaces need to be reasoned about
  together

Examples:

- shared session continuity
- shared report artifact continuity
- shared order lifecycle continuity

A dependency class is not:

- a local cluster
- a specific initialization package

### Package Frontier Slice

A package frontier slice is:

- the current bounded active unresolved work unit at the package floor

It may include:

- several clusters
- one or more initialization groups
- one or more DLLs
- one dependency class

It is the unit the package floor decides to spend on next.

It is not:

- the whole package
- one arbitrary DLL by default

---

## Success Metrics For “Boa Constrictor Is Working”

We need explicit measurable outcomes.

The architecture should be considered to be working when these start to happen:

### Metric 1: Imported-to-active ratio improves

Over time, the package should show:

- more imported lower-floor truth
- less active frontier work

### Metric 2: Frontier slices get smaller and more attributable

The active frontier should:

- shrink
- localize
- become easier to explain

### Metric 3: Cheap runs increasingly shape expensive runs

The first-floor shard passes should increasingly determine:

- what expensive work is run next

instead of humans or broad reruns doing that manually.

### Metric 4: Initialization groups become reusable

The system should stop rediscovering the same setup state repeatedly.

### Metric 5: Package reruns stop repaying easy truths

Later package runs should be spending on:

- hard unresolved slices

not:

- trivially rediscovered known surfaces

### Metric 6: Agent work slices become clearer

Agents should increasingly be assigned:

- explicit frontier slices

instead of:

- vague DLL-wide tasks

### Metric 7: Cost per verified upgrade drops

This is one of the most important product metrics.

If the boa constrictor architecture is working, then:

- the cost of each new trustworthy upgrade should decrease over time

---

## Strengths Of Implementing These Missing Systems

### Strength 1: Better first-run discipline

A real shard-intake system gives the first run an explicit purpose:

- organization before deep execution

### Strength 2: Better package splitting

The system becomes capable of reasoning in:

- groups
- states
- dependencies
- frontier slices

instead of defaulting to:

- DLLs

### Strength 3: Better agent usability

Explicit slice artifacts make it much easier for multiple strong agents to work
without flooding the main executor with undifferentiated context.

### Strength 4: Better product transfer

These are exactly the kinds of generic systems that can transfer beyond the
fixture suite into real enterprise packages.

---

## Weaknesses And Risks If We Build Them Poorly

### Weakness 1: Artifact explosion

If every shard emits too much low-quality structure, the merge system becomes
its own overload problem.

### Weakness 2: False grouping confidence

If shard merge is too eager, the system will build impressive-looking but wrong
groupings that poison later expensive runs.

### Weakness 3: Label drift

Without stable IDs and provenance, clusters and groups will become hard to
compare or reuse across runs.

### Weakness 4: Contoso overfitting

It is easy to make shard grouping logic that works beautifully on the fixture
suite but is too shaped by those fixtures.

---

## Why These Weaknesses Matter

These are not cosmetic concerns.

If the shard artifacts are weak, then:

- merge will be noisy
- frontier planning will be noisy
- agent work slices will be noisy
- expensive package work will still be chosen badly

So the system must be:

- contract-first
- provenance-heavy
- observer-backed
- explicit about confidence and ambiguity

That is how we turn this from a good idea into a real product-quality system.
