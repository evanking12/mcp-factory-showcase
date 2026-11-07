# Floor-to-Ceiling Iteration

## Why This Document Exists

The next scaling question is not only:

- what should the engine eventually be able to do?

It is:

- how should we build each floor of the engine so the next floor has a real
  chance to succeed?

This note describes the development model that follows naturally from the
priority-stack work:

- define the floor below clearly
- make it observable
- make it leave reusable artifacts
- only then tighten the floor above it

The goal is not to fully design every floor in advance as static prose.

The goal is to make each layer explicit enough that:

- it can be verified honestly
- it can support the next layer cheaply
- it does not force expensive rediscovery later

---

## Core Rule

Do not try to design the whole skyscraper at once.

Instead:

1. define the current floor as a contract-bearing layer
2. specify what it must produce for the next floor
3. verify that those outputs are real and reusable
4. only then define the next floor more tightly

That is how scale stays trustworthy.

---

## The Development Shape

The correct progression is:

- ground floor
- cluster floor
- composition floor
- package floor
- higher-order cross-DLL and larger-suite floors

Each floor should answer:

- what it must establish
- what artifacts it must export
- what observers declare it pass or fail
- what the next floor is allowed to assume

This means the engine should be built bottom-up through verified composition,
not top-down through broad ambition.

---

## Ground Floor

The ground floor is the first-pass foundation layer.

It should reliably establish:

- environment truth
- prerequisite producer truth
- read-surface truth
- state-machine shape
- handle and artifact families
- semantic sanity for reusable truth
- defer rules for hard or destructive targets

The ground floor should not try to prove everything.

Its purpose is to create safe reusable fuel for the next floor.

If the ground floor is weak:

- bad truth gets promoted
- later floors inherit poison
- repeat passes stay expensive

So the ground floor must answer:

- what is safe to preserve?
- what is still too weak to reuse?
- what should be deferred until stronger prerequisites exist?

---

## Cluster Floor

The cluster floor is where semantically coherent local systems become the unit
of progress.

A cluster floor should provide:

- a bounded seam
- a dominant state story
- exported artifact families
- satisfied invariants
- unresolved blockers
- trusted proof jobs
- expected next move

This floor is what makes local reruns:

- narrower
- cheaper
- less repetitive

If the cluster floor is weak:

- the engine falls back to whole-DLL or package-scale rediscovery
- agents cannot consume machine-readable progress safely
- carryover becomes harder to reason about

So the cluster floor must answer:

- what local truth is coherent enough to stand on its own?
- what artifacts leave the cluster?
- what must hold before adjacent work can trust it?

---

## Composition Floor

The composition floor is where local truth must survive when composed into a
larger whole.

Right now, this is the live frontier.

This floor should answer:

- did package mode preserve the strongest local truth?
- if not, where exactly was it lost?
- was the loss in:
  - finding recording
  - orchestration
  - verification
  - carryover routing
  - checkpoint hydration

This floor is critical because:

- local cluster truth is already stronger than package truth in some cases
- if local green cannot become package green, scale will remain expensive

So the composition floor must export:

- explicit carryover findings
- first broken handoff
- first broken invariant
- smallest failure scope

That is how later floors avoid treating package regressions as mystery events.

---

## Package Floor

The package floor is the first floor where a whole package campaign becomes a
real confirmation surface instead of a rediscovery surface.

This floor should answer:

- what lower-floor truths were imported instead of re-executed?
- what DLLs or functions remain the active package frontier?
- what package-level observers are allowed to veto a broad confirmation run?
- did the package run preserve imported truth or reopen it?

The package floor should import:

- reusable lower-floor DLL truth
- prerequisite-state group expectations
- frontier-only package plan data
- carryover and cohesion observer expectations

The package floor should export:

- a canonical `package-frontier-plan.json`
- package-facing truth and cohesion artifacts
- package-floor evidence class (`valid_frontier_rehearsal` vs `overlap_comparable_confirmation`)
- explicit confirmation gates and stop conditions
- campaign-level attribution that distinguishes imported truth from active work

The package floor should also preserve the active baseline contract whenever
the planner already knows it, so reduced frontier runs can become
comparison-safe without caller-memory patching.

This matters because a package run should not be treated as "all DLLs live by
default" once lower floors already proved reusable truths.

If the package floor is weak:

- package runs pay rediscovery cost again
- imported lower-floor truth looks indistinguishable from newly explored work
- carryover failures remain too ambiguous to route cheaply

So the package floor must answer:

- what was frozen and why?
- what remained active and why?
- what observer proved the package run stayed honest?

---

## Higher Floors

After the package floor, higher floors should be defined as explicit
composition contracts rather than as vague scale increases.

These include:

- DLL truth
- package truth
- narrow cross-DLL dependency classes
- larger-suite composition

Each higher floor should declare:

- what it imports
- what it exports
- what confidence is required
- what invariants must hold
- what observer declares pass or fail

That keeps scale from becoming:

- broader execution with weaker clarity

and instead makes it:

- broader composition with preserved trust

---

## Agents In This Model

This floor-to-ceiling model also gives the right shape for agent use.

The main thread should remain the only live executor.

Side threads should serve narrow purposes only:

- cluster state digestion
- carryover auditing
- artifact curation
- triage
- regression classification

Their job is to feed the main thread information.

They should not:

- compete on live execution
- widen scope on their own
- replace contract observers

The main thread should rely on their narrow analysis to reduce:

- context rebuild
- note burden
- decision latency

That is the correct operating shape:

- one executor
- many bounded observers and digesters

---

## What This Means Practically

The next logical architecture move is not:

- fully designing every future floor in exhaustive detail

It is:

- formalizing the contract chain between the first four floors:
  - ground floor
  - cluster floor
  - composition floor
  - package floor

That work should define, for each floor:

- success criteria
- exported artifacts
- observer surfaces
- allowed assumptions for the next floor

Once that exists, higher floors can be designed with much less ambiguity.

---

## Product Interpretation

This is not only an architecture model.

It is also the development-cycle model.

As the project scales up, iteration becomes harder because:

- there is more truth to preserve
- more hidden variables can leak across boundaries
- more expensive reruns are possible
- more context must be rebuilt before each decision

The floor-to-ceiling model is meant to control that cost by forcing each floor
to leave behind:

- reusable evidence
- explicit observers
- bounded failure localization
- honest next-floor assumptions

That is how the engine becomes both:

- more capable
- more efficient to improve

---

## The Guiding Question

For any proposed floor, ask:

- what must this floor reliably accomplish so the next floor has a real chance
  to succeed?

If that cannot be answered clearly, the floor is not ready to carry more
architecture yet.
