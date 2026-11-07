# Priority Stack to Live

## Why This Document Exists

This note turns the current scaling discussion into an implementation order that
is small enough to execute, strong enough to verify, and realistic enough to
support a live product path.

The goal is not to describe every desirable future subsystem.

The goal is to answer:

- what must come first
- why it must come first
- what each layer depends on
- what each layer changes in the pipeline
- what must be verified before building the next layer

This is an execution-order document, not just a vision document.

---

## Core Rule

Start small, verify, and build out.

That is the only reliable way this product will work.

The engine is already strong enough to prove that:

- capability exists
- coordination matters
- bounded reruns matter
- package density can expose hidden drag

What it does **not** yet prove is that the architecture can scale cheaply,
safely, and compositionally.

So the priority stack below is ordered by one principle:

- build the smallest layer that materially reduces wasted iteration without
  poisoning later reuse

---

## The Priority Stack

The recommended implementation order is:

1. truth-quality gating and pass scoping
2. machine-readable cluster checkpoints
3. package carryover subsystem
4. seeded bounded reruns as the default repeat-work path
5. first narrow cross-DLL contracts
6. multi-agent exploitation layer
7. package frontier planning and package-floor confirmation gating

This order is deliberate.

If these are built out of order, later layers become noisier, more expensive,
and less trustworthy than they need to be.

The new package-floor layer sits after the first floor-to-ceiling tranche and
before broad enterprise package expansion:

- a package campaign should import preserved lower-floor truths
- it should expose only the active frontier as live work
- it should treat full-package spend as confirmation rather than rediscovery

That means Batch B is no longer the identity of the planner. It is only the
current proving package for a generic package-frontier planning system.

---

## 1. Truth-Quality Gating and Pass Scoping

### Why This Comes First

This is the base of the base.

If the engine promotes bad truth into reusable truth, every later reuse layer
gets more dangerous.

If the first pass aims too broadly, the engine wastes time on hard write-heavy
or deeply stateful targets before the foundation exists to handle them
coherently.

So before scaling reuse, we need to tighten:

- what is safe to preserve
- what early passes are even allowed to try

### What This Layer Should Do

It should define:

- stronger promotion rules for reusable truth
- semantic plausibility checks in expected-vs-observed reporting
- explicit first-pass ambition rules
- explicit defer rules for hard targets

Pass 1 should focus on:

- environment setup
- prerequisite producers
- read surfaces
- state-machine shape
- handle and artifact families
- semantic sanity checks

Pass 1 should usually defer:

- destructive writes
- irreversible actions
- hard gated consumers
- deep downstream targets with weak prerequisites

### Strengths

- reduces wasted early exploration
- lowers the chance of upstream poison
- improves run economics immediately
- creates cleaner fuel for later checkpoints and seeded reruns

### Weaknesses Or Risks

- if scoped too narrowly, the first pass may become too timid
- if semantic gates are too strict, good early truth may fail to promote
- the engine may need several tuning cycles before the promotion threshold is
  balanced correctly

### What Must Be Verified

- a result cannot become seed-eligible merely because it returned success
- semantic family correctness is checked before promotion
- first-pass work spends more effort on producers and reads than hard writes
- early pass runtime decreases or becomes more predictable
- later passes inherit more useful foundation than before

### What Happens To The Pipeline

The pipeline becomes more incremental.

Instead of treating early runs as broad speculative unlock attempts, it starts
treating early runs as foundation-building passes.

This changes:

- exploration ambition
- promotion criteria
- when consumers are attempted
- what gets carried forward

### Dependencies

This layer depends on:

- expected-vs-observed reporting already existing
- system contracts already existing enough to define basic expected shapes
- current status and contradiction logic remaining canonical

It should **not** depend on:

- multi-agent infrastructure
- cross-DLL contract modeling
- large-scale new orchestration

---

## 2. Machine-Readable Cluster Checkpoints

### Why This Comes Second

Once truth quality and pass ambition are tightened, the engine needs a reusable
unit of progress smaller than a DLL and much smaller than a package.

That unit is the cluster.

Markdown notes are useful for humans, but not enough for automation or
consistent reuse.

So the next move is to turn cluster state into a canonical machine-readable
surface.

### What This Layer Should Do

A cluster checkpoint should capture:

- cluster id
- target seam or dominant state story
- latest trusted proof jobs
- current gate color
- exported artifact families
- satisfied invariants
- unresolved blockers
- reuse eligibility
- expected next move

This should become the canonical bounded unit for:

- local reruns
- observer results
- later seeding
- later carryover audits
- later agent consumption

### Strengths

- compresses evidence into a reusable semantic unit
- makes the next move easier to automate
- reduces context rebuild cost
- creates a lower-level checkpoint than stage-level state

### Weaknesses Or Risks

- poorly shaped clusters will create misleading checkpoints
- if the schema is too loose, it becomes non-diagnostic metadata
- if the schema is too strict, it becomes hard to adopt across different DLL
  families

### What Must Be Verified

- cluster checkpoint state is stable across repeated local reruns
- checkpoints are backward-tolerant with older artifacts where required
- a cluster checkpoint contains enough information for a new agent to resume
  without reading raw logs first
- cluster boundaries are behaviorally coherent, not just file-location-based

### What Happens To The Pipeline

The pipeline gains a new semantic unit of memory.

Instead of:

- stage state only
- package results only

it gains:

- bounded cluster memory

That changes:

- how evidence is preserved
- how local reruns are targeted
- how local success is defined

### Dependencies

This layer depends on:

- truth-quality gating being good enough that preserved cluster truth is worth
  trusting
- seam observers being strong enough to say whether the cluster is coherent

It is a prerequisite for:

- seeded rerun maturity
- carryover auditing
- useful agent specialization

---

## 3. Package Carryover Subsystem

### Why This Comes Third

This is the current live frontier.

Local cluster truth is already stronger than package truth in some cases.
That means the engine can prove things in bounded space but still lose them
when composing into package mode.

That is the exact drag that will destroy scaling if left untreated.

So after cluster checkpoints exist, the next critical move is to explain and
repair:

- why local green does not always become package green

### What This Layer Should Do

The carryover subsystem should explicitly inspect:

- same-run prereq success vs direct target persistence
- finding recording conflicts
- package orchestration overwrites
- verifier disagreement with probe truth
- cluster-green truth being dropped during package assembly

It should answer:

- did package mode preserve the strongest local truth?
- if not, exactly where was it lost?

### Strengths

- attacks the highest-value remaining scaling bottleneck directly
- turns expensive package regressions into explicit persistence problems
- increases trust that local progress is not being wasted

### Weaknesses Or Risks

- it can become another analysis layer without changing runtime behavior if
  designed too passively
- if not bounded carefully, it may blur the distinction between local cluster
  logic and package assembly logic
- it may expose multiple failure classes at once and need strong triage

### What Must Be Verified

- local green package-red mismatches can be explained by explicit carryover
  findings
- stronger same-run prereq truth is not overwritten by weaker direct target
  findings
- package-mode direct target budgeting preserves already-earned local truth
- the carryover subsystem reduces the number of package-only “mystery”
  regressions

### What Happens To The Pipeline

The pipeline gains a formal composition audit between:

- cluster truth
- package truth

This changes package execution from:

- broad orchestration with inferred persistence behavior

to:

- contract-bearing composition with explicit persistence checks

### Dependencies

This layer depends on:

- machine-readable cluster checkpoints
- observer-backed local green states
- enough package artifacts to compare local and package truth cleanly

It is a prerequisite for:

- confident larger package scaling
- meaningful cross-DLL composition work

---

## 4. Seeded Bounded Reruns As The Default Repeat-Work Path

### Why This Comes Fourth

This already exists in part, but it should become the normal repeat-work lane,
not a special-case tool.

This is where pass compression becomes measurable.

If repeated passes do not get materially cheaper, then the pipeline is still
paying too much for rediscovery.

### What This Layer Should Do

It should make repeated investigation default to:

- seed from trusted checkpoint
- focus on one cluster or one seam
- rerun only what is needed
- preserve convergence evidence pass-to-pass

This layer should also introduce explicit convergence metrics:

- time to first trustworthy proof
- time to local green
- time from local green to package green
- pass count to stable callable behavior

### Strengths

- directly lowers runtime and operator cost for repeated work
- makes pass-to-pass learning visible
- creates the first honest answer to whether the engine is converging

### Weaknesses Or Risks

- if seeded reuse is too permissive, it spreads upstream poison
- if seeded reuse is too conservative, it fails to save meaningful time
- without good checkpoint compatibility, older truth surfaces become hard to
  exploit safely

### What Must Be Verified

- repeated passes on the same target surface get materially cheaper
- fewer already-proven seams are rediscovered
- seeded reruns remain trustworthy, not just fast
- convergence metrics improve across real work, not synthetic demos only

### What Happens To The Pipeline

The pipeline shifts from:

- repeated cold discovery

to:

- progressive convergence

This is the main operational shift from demo behavior toward product behavior.

### Dependencies

This layer depends on:

- truth-quality gating
- cluster checkpoints
- carryover safety
- backward-tolerant checkpoint readers

It should come before:

- serious multi-agent exploitation
- large-suite scaling claims

---

## 5. First Narrow Cross-DLL Contracts

### Why This Comes Fifth

Cross-DLL dependency is probably the biggest future engineering hurdle, but it
should not be attacked as a giant framework first.

It should be approached narrowly, once cluster and package composition are
already behaving better.

The goal is to learn how to model cross-DLL composition without taking on the
entire 500-DLL problem at once.

### What This Layer Should Do

It should define a first narrow class of cross-DLL contracts such as:

- environment carryover
- handle or token reuse
- business-object continuity

Each such contract should define:

- exported artifacts
- imported expectations
- required confidence
- handoff invariants
- observer confirmation at the boundary

### Strengths

- begins solving the next true scaling wall
- turns package assembly into explicit composition
- makes larger package behavior less accidental

### Weaknesses Or Risks

- if done too early, it creates a large framework before the lower layers are
  stable enough to support it
- if done too broadly, it becomes an abstract taxonomy rather than a useful
  runtime surface
- it may expose significant hidden-variable complexity quickly

### What Must Be Verified

- one narrow cross-DLL dependency class can be modeled and observed cleanly
- exported truth can be consumed downstream without ambiguity
- package composition improves for that dependency class
- the contract remains generic and not campaign-specific

### What Happens To The Pipeline

The pipeline starts treating package composition as:

- explicit export/import contract assembly

instead of only:

- campaign orchestration and reuse

That is the beginning of true large-suite architecture.

### Dependencies

This layer depends on:

- stable cluster checkpoints
- stronger cluster-to-package carryover
- observer surfaces at package boundaries

It should come before:

- claiming serious 500-DLL readiness
- building many higher-order package planners

---

## 6. Multi-Agent Exploitation Layer

### Why This Comes Sixth

Agents are useful, but only after the substrate is ready.

If introduced too early, they mostly create:

- duplicated analysis
- more notes
- more orchestration overhead

instead of real speed gains.

The purpose of agents is to exploit stronger architecture, not substitute for
it.

### What This Layer Should Do

The multi-agent layer should stay mostly outside the pipeline and specialize
into narrow roles:

- one executor
- cluster owners
- one carryover auditor
- one strategy/triage role
- one artifact curator

Stable reusable roles should become skills.
Campaign-specific roles should stay as prompts or runbooks.

### Strengths

- reduces human context-rebuild cost
- speeds log digestion and triage
- improves planning while live runs are executing
- makes the main coordinator more effective

### Weaknesses Or Risks

- does not materially reduce live run wall-clock time by itself
- can create noise if roles are vague
- can tempt the system into parallelizing execution when only thinking should
  be parallelized

### What Must Be Verified

- each role has a narrow input and output
- only one role owns the live lane
- analysis threads reduce decision latency measurably
- the added agent layer does not increase contradiction or orchestration churn

### What Happens To The Pipeline

Strictly speaking, the pipeline itself changes little.

What changes is the operating model around it:

- more parallel analysis
- better note quality
- better post-run triage
- less human waiting with no conclusion

### Dependencies

This layer depends on:

- machine-readable cluster checkpoints
- clearer carryover surfaces
- stronger rerun gating
- enough stable operational doctrine to assign roles cleanly

It should remain downstream of the substrate layers.

---

## The Smallest Viable First Tranche

If only one small tranche is built next, it should be:

1. narrow pass-1 ambition law
2. machine-readable cluster checkpoint schema
3. package carryover audit for residual package-only regressions
4. convergence metric for repeated passes on the same cluster

Why this tranche first:

- it directly improves cost per iteration
- it reduces the risk of poisoned reuse
- it exposes whether the pipeline is actually learning faster
- it improves the exact frontier that current Batch B results revealed

This is the smallest tranche that is both:

- strategically correct
- immediately useful

---

## What Success Looks Like

The priority stack is working if:

- pass 1 becomes narrower and cheaper
- cluster checkpoints become the normal unit of progress
- local green truth is preserved into package mode more reliably
- repeated passes compress in time and scope
- one narrow cross-DLL contract works cleanly
- agents accelerate decision quality instead of inflating chatter

The stack is failing if:

- early passes still chase hard writes too broadly
- seeded reruns are fast but semantically untrustworthy
- package mode still drops local truths with no explanation
- cross-DLL composition remains accidental
- more agents create more output but not faster convergence

---

## Final Reading

This is a large engineering challenge.

That is exactly why the implementation order matters so much.

The product will not be brought to life by one giant leap.
It will be brought to life by:

- a safer base
- tighter bounded memory
- stronger carryover
- cheaper repeated passes
- explicit composition
- then selective operational parallelism

That is how the system gets from:

- impressive capability

to:

- live, scalable, economically workable product behavior
