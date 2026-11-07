# Engine Scaling and Product Horizon

## Why This Document Exists

This document defines the next architecture horizon after the current Batch B
success.

The old question was:

- can the engine recover behavior on a dense synthetic package?

The new question is:

- can the engine scale to large real-world suites without becoming too slow,
  too expensive, or too opaque to improve?

That is the actual product boundary.

---

## Current Best Product Milestone

Current best architecture checkpoint is no longer only a verified-count number.

The stronger milestone now is:

- floor-to-ceiling is a real runnable control surface
- package frontier planning exists as a generic concept in pipeline core
- Batch B can run with imported lower-floor DLL truths and a narrow active
  frontier instead of treating every DLL as equally live

That is a better product-horizon milestone than an older package count alone,
because it proves the engine is starting to reduce rediscovery cost rather than
only broadening raw capability.

What it proved:

- scale pressure is increasingly a preservation and package-planning problem
- campaign orchestration can distinguish imported lower-floor truth from active
  frontier work
- control-surface maturity now matters more than another speculative broad run

What it still does **not** prove:

- that cross-DLL interwoven enterprise packages are cheap yet
- that the package carryover and verification handoff is fully trustworthy
- that enterprise package planning is generic enough without further hardening

The main architectural lesson remains:

> Scale is not only a capability problem. It is a control, compression, and run
> economics problem.

---

## Product Thesis

The product statement still holds:

> Give us a Windows enterprise DLL or DLL suite.
> We produce a verified OpenAPI document.
> You can generate an MCP server from that document.
> Your AI agent can now call legacy native software without vendor source code
> and without hand-written integration code.

But after Batch B, the practical product thesis is sharper:

> The engine is only commercially viable if it can improve and re-run at scale
> without requiring many hours of operator time or repeated expensive
> end-to-end campaigns.

That means scale planning must optimize two things at once:

- capability breadth
- decision quality per hour and per dollar

---

## The Real Next Barrier

The biggest hurdle between an impressive demo and a chargeable MVP is no longer
"can the engine do something clever on a package."

It is:

- can the engine stay trustworthy at larger function counts
- can it localize problems cheaply
- can it re-run selectively instead of globally
- can it preserve useful evidence between iterations
- can it tell us what to fix next without multi-day forensic work

That is why the next architecture phase should not be framed as "just scale to
500 functions."

It should be framed as:

- make 500-function operation economically and diagnostically feasible

---

## The Three Immediate Architecture Priorities

### 1. Run economics as a first-class architecture surface

The engine must be designed around the cost of learning, not only the cost of
executing.

At larger function counts, success metrics must include:

- trustworthy coverage gained per hour
- trustworthy coverage gained per dollar
- number of local seam cycles per full-package run
- amount of reusable evidence captured per run
- number of expensive reruns avoided by narrow checkpoints

If these do not improve, larger function counts are not a product milestone.

### 2. Cluster-level checkpoints and observer-gated iteration

Large suites cannot be treated as one giant probe context.

The unit of iterative progress must become the **cluster**, not the whole DLL or
whole package.

A cluster is a semantically coherent group of functions that share enough of the
following to be worth reasoning about together:

- common state prerequisites
- common handles, ids, or artifact families
- common namespace or export prefix
- common domain behavior
- common error vocabulary

Examples:

- pricing quote lifecycle cluster
- reporting preview/render cluster
- transport session/open/send cluster
- config approval/license cluster

Each cluster should have:

- a compact checkpoint
- expected-vs-observed seam observers
- cluster-local rerun surfaces
- explicit carry-forward artifacts for adjacent clusters

The goal is to spend most iteration budget at the cluster level and use
full-package runs mainly as confirmation.

### 3. System contracts and observers as scale prerequisites

System contracts and seam observers are no longer just a Batch B fix tactic.

They are the first scalable answer to:

- how systems cooperate under pressure
- how failures are localized cheaply
- how rerun gates become explicit instead of intuitive

The rollout sequence should remain:

1. contract-bearing systems
2. observer-bearing seams
3. agent-bearing automation

This is what makes later automation agents useful rather than noisy.

---

## Internal Operators As A Future Scale Layer

The first useful agent layer should remain **outside** the pipeline:

- orchestration
- triage
- comparison
- reporting
- bounded execution control

That preserves trust because the pipeline remains the measured system and the
operator layer remains the thing coordinating it.

But there is also a plausible future class of **internal operators** that live
inside the pipeline itself.

These should not be freeform autonomous agents. They should be explicit,
contract-bound operator subsystems that are:

- evidence-producing
- replayable
- auditable
- bounded in authority
- easy to disable or bypass

Good candidates include:

- checkpoint reuse selectors
- contradiction classifiers
- carryover auditors
- package-mode persistence diagnosticians
- bounded seam-fault classifiers

The right internal-operator rule is:

- outside the pipeline first for governance and throughput
- inside the pipeline later only where the behavior can be made explicit,
  contract-bearing, and diagnostically useful

The most promising future internal operator is likely a **carryover operator**
that explains why locally green truths failed to persist into package mode.
That maps directly to the current frontier:

- seeded reuse quality
- cluster-to-package persistence
- cost per trustworthy iteration

So internal operators make architectural sense, but only after they stop
looking like "agents" and start looking like bounded internal operator systems.

---

## What A Cluster Actually Entails

A cluster is not just "a random subset of functions."

A good cluster has:

- one dominant state story
- a bounded set of producer-consumer chains
- a bounded evidence vocabulary
- a small number of adjacent clusters
- a checkpoint compact enough to load as dense context

A cluster should answer:

- what functions belong together
- what live artifacts are produced inside it
- what artifacts are exported for neighbors
- what invariants must hold before leaving it
- what local observer surfaces tell us it is coherent

Bad clusters are:

- too broad to fit in a compact checkpoint
- too narrow to preserve state meaning
- mixed across unrelated state machines
- defined only by file location rather than behavioral coherence

The point of clustering is not bookkeeping. It is evidence compression with
semantic integrity.

---

## What Evidence Compression Must Mean

Evidence compression is not "store less text."

It means:

- preserve the reusable truths
- discard the dead exploratory noise
- keep enough lineage to trust the checkpoint later

A useful cluster checkpoint should preserve:

- verified producers and consumers
- live artifact families
- first broken invariants
- reliable error classes
- state-machine progress markers
- contract version and evidence schema version

A bad checkpoint is one that is compact but no longer diagnostic.

---

## Reuse-First Iteration Principle

The most important operational lesson from Batch B is simple:

- if the engine must wait for a full expensive rerun to learn each next thing,
  scale will fail before capability does

Expensive reruns are expensive in two ways:

- money
- operator time

That means the engine must increasingly treat prior successful work as reusable
fuel for the next run, not as history to be re-derived from scratch.

The principle should be:

- capture useful truth once
- compress it safely
- seed the next bounded run with it
- spend full-package reruns only when the local evidence surface says the next
  package confirmation is worth the cost

This is not an optimization after scale. It is a precondition for scale.

---

## Pre-Seeding New Runs With Prior Truth

The next iterations of the pipeline should explicitly support:

- seeding a new job with a previous finished job or cluster checkpoint
- reusing prior verified producers, artifact families, state-machine markers,
  and environment facts
- carrying forward expected-vs-observed seam knowledge from prior runs

This should remain generic:

- no fixture-specific shortcuts
- no blind acceptance of old evidence
- all reused evidence must carry lineage, schema version, confidence, and
  allowed reuse scope

The value of pre-seeding is not only speed. It also reveals a deeper product
truth:

> In a perfect pipeline, how early could this function or cluster be cracked if
> the engine started with the best trustworthy prior context?

That question is extremely valuable because it helps separate:

- capability gaps
- checkpoint/compression gaps
- coordination gaps
- rerun strategy waste

If a target becomes easy once seeded with prior trustworthy context, then the
problem is not raw invocation capability. It is how poorly the engine preserves
and reuses what it already learned.

---

## Cluster Checkpoints Are Lower Than Stage Checkpoints

Yes. Cluster checkpoints should be treated as a lower-level checkpoint surface
than stage checkpoints.

Stage checkpoints answer:

- what the stage produced
- what the next stage may trust

Cluster checkpoints answer:

- what a semantically coherent function cluster learned
- what adjacent clusters may reuse
- what local seam invariants are already satisfied
- what unresolved local blockers remain

This lower-level checkpoint depth is important for future automation because it
gives observer agents a smaller and more meaningful unit to inspect than:

- an entire stage
- an entire DLL
- or an entire package

That is what makes autonomous investigation operationally plausible instead of
too broad and expensive.

---

## What Documentation, Skills, And Agents Need To Exist

To capture this principle in the actual engine, the repo needs three new
categories of control surface.

### Documentation

The scaling doctrine should explicitly define:

- cluster formation rules
- cluster checkpoint schema
- evidence seeding rules
- reuse eligibility rules
- observer-gated rerun policy
- run-economics metrics

This document is the strategic layer. It should be paired later with an
execution-facing cluster/checkpoint design spec.

### Skills

Future skills should likely include:

- cluster-checkpoint auditor
  - checks whether a checkpoint preserves enough reusable truth without losing
    diagnosability
- seeded-run planner
  - decides how to seed a new bounded run from prior trustworthy evidence
- run-economics auditor
  - evaluates whether a rerun plan is too expensive for the evidence it is
    expected to produce

These should come only when the underlying schema and observer surfaces exist.

### Agents

Future narrow agents should be able to:

- watch one cluster checkpoint lineage
- compare expected vs observed seeded reuse
- decide whether a failure is due to:
  - bad seeding
  - stale evidence
  - broken local coordination
  - real capability gap
- write a bounded finding for the coordinator

This is how overnight automation becomes multiplicative instead of chaotic.

---

## What Automation Should Eventually Do

Automation should come after contracts and observers, not before them.

The eventual role of narrow automation agents is:

- monitor one contract-bearing system or one observer-bearing seam
- compare expected vs observed behavior
- decide whether the likely fault is local, upstream, downstream, or shared
- write structured findings
- inform the next bounded rerun decision

This is how overnight work becomes scalable without becoming chaotic.

Agents should not begin as free-form mini-architects. They should begin as
bounded contract observers.

---

## Priority Order For The Next Phase

| Priority | What | Why |
|---|---|---|
| 1 | **Cluster and checkpoint architecture** | This is the real scale bottleneck |
| 2 | **System-contract and observer rollout** | Makes clusters diagnosable and reruns cheaper |
| 3 | **Run-economics instrumentation** | Makes scale success measurable in time and cost |
| 4 | **OpenAPI emitter from verified evidence** | Converts engine output into the real product surface |
| 5 | **Real named target demo (Sabre or equivalent)** | Replaces Contoso in product conversations |
| 6 | **Analyzer adapters (COM, .NET, Linux)** | Valuable, but only after scale control is real |

The important change from earlier thinking is:

- OpenAPI is still essential
- but scale control and iteration economics come first

Without them, the engine can still be impressive and unusable.

---

## Scale Foundation Implementation Order

The next broad scale layer should be built in this order:

1. system contracts
2. seam observers
3. cluster checkpoints
4. seeded bounded reruns
5. observer and agent automation on top

This order is deliberate. Each layer depends on the one before it.

### 1. System Contracts First

System contracts come first because everything else needs a shared control
vocabulary.

What to implement first:

- one canonical contract schema in pipeline core
- rollout across real systems, not only the current Batch B seam
- required contract fields for:
  - consumes
  - emits
  - decisions
  - handoff invariants
  - required evidence
  - success signals
  - failure signals
  - expected test surfaces

Why first:

- observers are otherwise just smarter log scraping
- clusters do not have precise expected behavior
- seeded reuse has no trustworthy reuse boundary

System contracts are the first control layer.

### 2. Seam Observers Second

Once contracts exist, the repo should deepen expected-vs-observed observer
surfaces on the highest-pressure seams.

What to implement first:

- config approval and license paths
- workflow state and handle continuity
- pricing quote, state, and seal paths

Each observer should emit:

- expected handoff
- observed handoff
- first invariant break
- likely local vs upstream vs downstream failure

Why second:

This is the first real iteration-speed multiplier.

It converts:

- "the package regressed"

into:

- "this handoff broke here"

It also makes rerun gates explicit instead of intuitive.

### 3. Cluster Checkpoints Third

After contracts and observers exist, the repo should introduce a lower-than-
stage checkpoint unit.

What to implement first:

- cluster definition rules
- one cluster checkpoint schema
- first clusters should be obvious current state machines such as:
  - pricing quote lifecycle
  - workflow reservation/open/confirm/state
  - config approval/license

Each cluster checkpoint should store:

- verified producers and consumers
- live artifact families
- satisfied invariants
- unresolved blockers
- lineage
- reuse eligibility

Why third:

This is the first real scale primitive.

It lets the engine preserve meaning below the stage level and rerun only a
semantically coherent unit instead of a whole DLL or package.

It also gives future automation agents a sensible work unit.

### 4. Seeded Bounded Reruns Fourth

Once cluster checkpoints exist, bounded runs should be able to start from prior
trusted truth.

What to implement first:

- seed-from-prior-checkpoint rules
- reuse eligibility rules
- lineage, schema-version, and confidence checks
- bounded rerun entrypoints that say:
  - start from this checkpoint
  - probe only this cluster or adjacent seam
  - do not rerun the world

Why fourth:

This is where scale economics improve materially.

It reduces:

- time per useful conclusion
- cost per useful conclusion
- reliance on cold full-package reruns

But it is dangerous if done too early. Without contracts, observers, and
cluster checkpoints, seeded reuse just spreads stale evidence faster.

### 5. Observer And Agent Automation Last

Automation should sit on top of the previous layers, not replace them.

What to implement first:

- narrow agents that monitor one cluster or seam
- each agent should report:
  - expected vs observed
  - local vs upstream vs downstream blame
  - whether another bounded rerun is justified

These should be bounded contract observers, not free-form mini-architects.

Why last:

Before the lower layers exist, more agents create more noise.

After the lower layers exist, they become multiplicative:

- faster local analysis
- more consistent blame boundaries
- cheaper overnight progress

### Recommended Immediate Slice

If choosing the next concrete implementation tranche today, the best first
slice is:

- deepen system contracts and seam observers on the 6 remaining Batch B
  overlap regressions
- then define the first cluster checkpoint schema from those same seams

Why:

- it gives immediate product value
- it helps finish Batch B
- it builds the exact substrate needed for later seeded reruns and automation

---

## What Must Be True Before Calling It A Product

Before this becomes a chargeable MVP, the engine should be able to do all of the
following on a meaningful non-Contoso target:

- operate on large suites through clusters instead of one giant context
- preserve evidence through compact checkpoints
- rerun locally before rerunning globally
- explain failures at the seam level, not only at package level
- show improving trustworthy coverage without requiring repeated multi-hour
  operator intervention
- emit a product output surface such as OpenAPI from verified evidence

That is the real bridge from:

- technically differentiated demo

to:

- operationally viable product

---

## The Main Architectural Warning

The easiest mistake from here is to treat larger function counts as the next
headline metric.

That would be wrong.

The next headline metric should be something closer to:

- trustworthy coverage gained per cluster rerun
- trustworthy coverage gained per hour
- percentage of issues localized without full-package rerun
- percentage of new progress achieved through seeded bounded reruns instead of
  cold full-package campaigns

Those are the metrics that tell us whether the engine is becoming commercially
deployable, not just more impressive in isolated demos.
