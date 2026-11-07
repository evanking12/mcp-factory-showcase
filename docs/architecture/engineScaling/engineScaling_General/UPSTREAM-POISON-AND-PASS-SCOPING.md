# Upstream Poison and Pass Scoping

## Why This Document Exists

As the engine gets better at preserving and reusing prior truth, two scaling
risks become more important:

- bad truth can spread farther
- early passes can waste too much effort on targets they have not yet earned

These are both run-economics problems.

If we improve reuse without improving truth quality, the engine can fail faster
and more confidently.

If we let the first pass aim too broadly, the engine can spend too much time
trying to unlock hard write-heavy targets before the state foundation is ready.

So the next scaling step is not only:

- better carryover

It is also:

- safer carryover
- better pass ambition discipline

---

## Upstream Poison

Upstream poison means the pipeline promotes a low-quality, semantically wrong,
or misleadingly "successful" result into reusable truth.

Once that happens, later systems may treat nonsense as authority.

That poison can then spread through:

- seam observers
- cluster checkpoints
- seeded bounded reruns
- package carryover
- later verification and tuning passes

This is the danger of stronger reuse without stronger truth standards.

The risk is not just:

- "the call returned success"

The risk is:

- the call looked successful enough to be reused
- but the underlying output was semantically wrong
- and later passes built on top of it

That is worse than a local failure because it contaminates future learning.

---

## What A Better Truth Standard Must Require

For reusable truth, procedural success is not enough.

Seed-eligible or carryover-eligible truth should increasingly require:

- procedural success
- semantically plausible outputs
- family-correct identifiers and artifacts
- non-contradictory reuse behavior
- alignment between expected and observed output shape
- evidence that the success is not merely a stale or accidental replay artifact

In other words:

- a result should not become authoritative just because it "returned 0"

It should become authoritative only when the engine has enough evidence to
believe the returned state is meaningful.

---

## The Foundational Pass Is Still Too Broad

The current foundational pass can still spend too much effort on targets that
are too ambitious for the amount of context available.

That often means:

- hard writes
- heavily gated consumers
- stateful commits
- deep downstream targets

being attempted before the engine has enough truth about:

- environment setup
- handle and token families
- prerequisite producers
- state-machine shape
- stable readable state surfaces

This is expensive in both runtime and operator attention.

It also weakens later passes because the first pass spent too much effort on
calls that were unlikely to become trustworthy that early.

---

## What The First Pass Should Actually Aim For

The first pass should be narrower and more deliberate.

It should mostly try to establish:

- environment and setup truth
- stable prerequisite producers
- readable state surfaces
- handle, token, ticket, nonce, and id families
- state-machine structure
- low-risk read functions
- early semantic validation of outputs

It should usually avoid or defer:

- destructive writes
- irreversible actions
- deep stateful commits
- consumers whose prerequisites are still weak
- expensive branches that depend on unproven artifact families

The first pass should earn the right to attempt the harder work later.

---

## Pass Roles Should Be Different

Different passes should have different jobs.

### Pass 1

Primary goal:

- establish foundational truth

Focus:

- environment
- producers
- read surfaces
- state shape
- semantic sanity checks

### Pass 2

Primary goal:

- use the first-pass truth to unlock bounded producer-consumer chains

Focus:

- stronger handoffs
- seeded local reruns
- bounded stateful consumers

### Pass 3

Primary goal:

- validate harder consumers and cluster coherence

Focus:

- write-capable consumers
- cluster-green confirmation
- observer-backed persistence checks

### Later Passes

Primary goal:

- package confirmation and carryover hardening

Focus:

- package-mode persistence
- cluster-to-package promotion
- residual edge-case cleanup

This is the correct way to "eat the pizza":

- one bite at a time
- with each bite enabled by the ones before it

---

## Why This Matters For Productization

If the first pass stays too broad, the engine keeps paying for low-probability
work too early.

If bad truth can become reusable truth, stronger carryover will amplify the
wrong things.

So a scalable product has to get both right:

- what truth is safe to preserve
- what ambition level each pass is allowed to have

That is how the engine becomes:

- cheaper to iterate
- safer to reuse
- more incremental
- less dependent on broad speculative exploration

---

## Immediate Architectural Direction

The next refinement layer should include:

- stronger semantic promotion rules for reusable truth
- explicit upstream-poison detection in expected-vs-observed reporting
- narrower first-pass objectives
- clearer defer rules for hard write-heavy targets
- pass-specific ambition law

The engine should increasingly behave like an incremental learning system:

- first build the foundation
- then unlock bounded seams
- then confirm cluster coherence
- then spend package-scale budget

That is the path from expensive rediscovery to controlled convergence.
