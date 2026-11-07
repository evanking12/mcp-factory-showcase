# Convergence Rate and Pass Compression

## Why This Document Exists

The next scaling question is not only:

- can the engine eventually recover callable behavior?

It is also:

- does the engine get materially cheaper and faster each time it revisits the
  same target surface?

That is the practical difference between:

- a pipeline that is learning
- and a pipeline that is repeatedly rediscovering

If repeated passes on the same DLL, cluster, or function family remain close to
the same cost profile every time, then more agents and more orchestration do
not actually solve the product problem.

---

## The Core Principle

A healthy scaled pipeline should not merely succeed after enough attempts.

It should converge.

That means:

- pass one is the most expensive
- later passes inherit prior truth safely
- later passes become narrower
- later passes become faster
- later passes spend less operator time and less runtime cost

The goal is not just:

- more verified functions

The goal is:

- more verified functions with an improving convergence curve

---

## What Pass Compression Means

Pass compression means that revisiting the same target surface should cost less
than the prior visit because the pipeline preserved useful truth from earlier
work.

Ideal shape:

- pass 1: broad expensive discovery
- pass 2: seeded local correction
- pass 3: narrow confirmation
- pass 4: almost no rediscovery overhead

Illustrative example:

- pass 1: 2 hours
- pass 2: 45 minutes
- pass 3: 30 minutes
- pass 4: 20 minutes

The exact numbers do not matter as much as the shape:

- each pass should shrink materially if carryover and checkpointing are working

If instead the shape looks like:

- 2 hours
- 2 hours
- 2 hours
- 2 hours

then the system is not learning efficiently enough, even if verified count
eventually improves.

---

## Why This Matters More Than Raw Agent Count

Adding more Codex threads or more analysis layers is only worthwhile if the
system's next pass becomes cheaper or more decisive.

Otherwise, parallelism only increases:

- chatter
- note volume
- orchestration overhead
- duplicated analysis

without materially reducing:

- time to the next trustworthy conclusion
- time to green
- cost per recovered function

So the scale question is not:

- how many agents can we run?

It is:

- how much does the next pass compress because prior truth was preserved well?

---

## What Must Improve To Make Pass Compression Real

Pass compression depends on:

- cluster checkpoints
- seeded bounded reruns
- carryover of locally green truth into package mode
- observer-backed seam attribution
- backward-tolerant checkpoint readers
- explicit contract surfaces between clusters and package mode

If these are weak, the engine pays for rediscovery on every pass.

If these are strong, the engine should:

- rebuild less state
- retry fewer already-proven seams
- reuse stronger producer truth
- route directly to the remaining broken handoff

---

## The Right Product Question

For any meaningful target surface, the correct question is:

- how many passes should it take to converge to stable callable truth?

Then:

- what should the cost of each successive pass be?
- where is the lower bound?
- how close is the pipeline getting to that lower bound?

That is how we determine whether the pipeline is behaving like a real product
instead of an expensive research loop.

---

## What Should Be Measured

The engine should eventually treat these as first-class scale metrics:

- time to first trustworthy local proof
- time from first proof to local green
- time from local green to package green
- pass count to stable callable behavior
- percent reduction in runtime cost from pass N to pass N+1
- percent reduction in operator interpretation time from pass N to pass N+1
- number of seams rediscovered unnecessarily on later passes

These matter alongside:

- verified count
- overlap delta
- contradiction count

---

## The Immediate Architectural Implication

The next development priority should not be "more agents first."

It should be:

1. improve carryover
2. improve cluster checkpoints
3. improve seeded rerun reuse quality
4. improve cluster-green to package-green persistence
5. then use agents to exploit those gains

That sequence is what makes multi-agent help meaningful instead of noisy.

---

## Product Standard

A scalable pipeline should increasingly behave like this:

- broad first pass
- narrower second pass
- cheaper third pass
- fast final confirmation

If repeated passes do not compress materially, the engine is still too close to
a demo.

If repeated passes do compress materially, the engine is starting to behave
like a chargeable product.
