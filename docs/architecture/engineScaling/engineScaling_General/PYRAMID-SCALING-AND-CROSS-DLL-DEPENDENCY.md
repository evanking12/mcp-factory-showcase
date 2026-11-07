# Pyramid Scaling and Cross-DLL Dependency

## Why This Document Exists

The likely scaling path for this engine is not:

- understand 10,000 functions in one giant run

It is:

- many small passes
- forming coherent clusters
- clusters forming coherent DLL truth
- DLL truth forming coherent package truth
- packages composing into much larger suites

This is the "great pyramid" model.

The base takes the longest to build because it contains the most raw discovery,
state establishment, and evidence shaping. But once the lower layers are
strong, later layers should become narrower and more compositional.

That is the practical way to think about 500 DLLs or 10,000 functions.

---

## The Pyramid Model

The engine should scale by gradually assembling larger wholes from smaller
trustworthy units.

### Layer 1: Small passes

Small passes should establish:

- environment truth
- prerequisite producers
- read surfaces
- state-machine shape
- artifact families

### Layer 2: Clusters

Clusters should establish:

- coherent producer-consumer chains
- observer-backed seam truth
- reusable cluster checkpoints
- bounded local green states

### Layer 3: DLL-level truth

DLL-level truth should establish:

- stable cluster composition inside one DLL
- shared state and artifact continuity inside that DLL
- local package-readiness

### Layer 4: Package truth

Package truth should establish:

- successful composition across multiple DLLs
- preserved carryover across cluster and DLL boundaries
- overlap-stable package behavior

### Layer 5: Large-suite truth

Large-suite truth should establish:

- repeatable composition across many packages and many DLL families
- manageable operator cost
- scalable diagnosis when something breaks

This is how the engine should "chew through the pizza":

- one bite at a time
- with each bite forming a stable part of the whole

---

## Why Batch B Matters Here

Batch B already showed the key lesson:

- the engine can choke on density before it reaches its theoretical capability

The issue was not simply:

- 86 functions is too many in the abstract

The issue was:

- package coordination
- carryover
- state continuity
- seam observability

were not yet strong enough for that density.

So the real question at larger scale is not:

- how many functions can we throw into one run?

It is:

- how much trustworthy composition can the system preserve as density rises?

That is why getting from 86 toward 100 or 150 functions per run is meaningful.
It is not only about bigger counts. It is about proving that the lower layers
of the pyramid are getting strong enough to support larger composition.

---

## The Biggest Future Hurdle: Cross-DLL Dependency

Cross-DLL dependency is likely the biggest engineering hurdle between
medium-scale package success and true large-suite productization.

At small scale, many problems still look local:

- one cluster
- one DLL
- one bounded seam

At larger scale, the danger becomes:

- hidden-variable explosion across boundaries

That is where the pyramid can collapse if the cross-DLL layer is weak.

---

## What We Already Have

The repo is not starting from zero on cross-DLL concerns.

We already have:

- campaign and package execution surfaces
- overlap comparison
- cross-DLL seeding behavior
- run-ledger attribution
- package-mode comparison
- package-level topology views
- cross-DLL evidence auditing as a recognized governance need

So cross-DLL work already exists in:

- attribution
- reuse
- campaign composition
- package behavior

That is a real foundation.

---

## What We Do Not Yet Have Strongly Enough

What is still missing is the most important architectural layer:

- first-class cross-DLL dependency contracts

Right now, cross-DLL dependency is handled more as:

- reuse
- attribution
- orchestration
- package behavior

than as:

- explicit exported artifacts
- explicit imported artifacts
- explicit cross-DLL handoff invariants
- explicit package-boundary observers

That is why larger-scale composition is still fragile.

---

## What Cross-DLL Architecture Will Need

The next serious scale layer should define:

- what truth one cluster or DLL can export
- what truth another cluster or DLL may import
- what confidence level is required
- what invariants must hold across the boundary
- what observer surfaces confirm the handoff stayed valid

The main dependency classes will likely include:

- environment carryover
- handle and token reuse
- state-machine continuation
- business-object continuity
- shared config and license state
- session continuity
- package-level prerequisite inheritance

This means a DLL should not merely "happen to help" another DLL.

It should explicitly say:

- what it can export
- in what shape
- with what confidence
- for which downstream consumers
- under what conditions

That is how package truth becomes compositional instead of accidental.

---

## Why This Matters For 500 DLLs

At very large scale, function count alone is not the real danger.

The real danger is:

- hidden variables
- accidental coupling
- poisoned reuse
- ambiguous carryover
- no clean way to localize failure between neighboring components

Without first-class cross-DLL contracts, a 500-DLL system can become a giant
surface of plausible but expensive confusion.

With stronger cross-DLL contracts, the large-suite problem becomes more like:

- assembling and validating known layers of the pyramid

instead of:

- hoping the whole structure does not collapse under density

---

## The Right Near-Term Direction

The next practical scale sequence should be:

1. keep shrinking pass size
2. keep improving cluster checkpoints
3. keep improving cluster-green to package-green carryover
4. introduce explicit cross-DLL export/import contracts
5. add cross-DLL observers at package boundaries

That is the path from:

- moderate package success

to:

- large-suite compositional success

---

## Product Reading

The pyramid model is the right long-term mental model.

We are still far from true 500-DLL scale.

But the important thing is that the next barrier is now clearer:

- not just more capability
- not just more functions
- but stronger cross-DLL composition

That is likely the hardest future engineering problem.

And it is also the problem that will most clearly separate:

- a strong demo

from:

- a real large-scale product
