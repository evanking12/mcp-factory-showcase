# Contoso Proving-Ground Expansion

## Scope Note

This document remains the standing review surface for the
`engineScaling_PipelineIterations` prompt chain and decomposition follow-up
work.

For interwoven-expansion work specifically, the primary prompt and dynamic
review surface is now:

- `docs/architecture/engineScaling/engineScaling_Interwoven/INTERWOVEN-METHODOLOGY-AND-GENERIC-SYSTEM-DIRECTION.md`

Use that interwoven document when the main changing variable is interwoven
dependency handling rather than the broader boa-constrictor decomposition
stack.

## Why This Document Exists

The current architecture tranche is being proven primarily on the Contoso
fixture suite.

That is useful because Contoso is:

- controlled
- repeatable
- cheap to run
- already shaped to the current pipeline

But it is also a risk because Contoso can become a false comfort surface:

- grouping logic may overfit to its topology
- initialization inference may look stronger than it really is
- decomposition systems may appear coherent only because the package family is
  familiar
- operator-facing observability may seem sufficient until a noisier enterprise
  system exposes missing fields or weak boundaries

So the question:

> "how do we expand beyond the current Contoso proving ground without losing control?"

should not be deferred until after the entire boa-constrictor tranche is
implemented. It should be asked after each prompt implementation while the
systems are still small enough to correct.

## Recommendation

This is a smart idea now, not later.

Why:

- the decomposition systems are new and easy to overfit
- the cheapest time to catch Contoso-shaped assumptions is immediately after
  each bounded prompt
- the whole point of boa constrictor is to make the pipeline more generic and
  more scalable, so proving only against one familiar family is not enough

What this document should do:

- act as a standing review surface after each prompt implementation
- force us to say what Contoso proved, what it did not prove, and what an
  enterprise system would likely expose
- identify stress tests while the implementation seam is still fresh

What this document should not do:

- block prompt execution before Phase 0 begins
- force us to invent a full enterprise corpus before the decomposition systems
  exist
- replace the existing architecture docs or weakness register

## How To Use This Document

After completing each prompt in
`docs/architecture/engineScaling/engineScaling_PipelineIterations/prompts/`,
append a short review under the corresponding section below.

For each prompt, answer these three questions:

1. What does Contoso prove right now?
2. What would we expect to be harder, noisier, or different in an enterprise system?
3. What stress test should we add now so the pipeline breaks here instead of later?

If the answer reveals a recurring architectural risk, also tighten:

- `.agents/ARCHITECTURAL-WEAKNESSES.md`
- `BOA-CONSTRICTOR-PACKAGE-DECOMPOSITION.md`
- `BOA-CONSTRICTOR-SYSTEM-CONTRACTS.md`

## Review Template

Use this template after each prompt implementation:

### Prompt `<id>` Review

- `What Contoso proves now:`
- `What enterprise pressure will likely expose:`
- `Stress test to add now:`
- `What would count as failure here:`
- `What downstream prompt would be poisoned if we ignore this:`
- `Did this reveal a new weakness worth promoting into the weakness register?`

### Prompt 00 Review

- `What Contoso proves now:` The Contoso proving ground is sufficient to lock
  one generic Phase 0 rail surface for decomposition lifecycle IDs,
  contradiction states, shard economics, observer payloads, and retention
  classification without depending on any one Contoso DLL family or package
  lane.
- `What enterprise pressure will likely expose:` Real enterprise packages will
  create more lifecycle churn, more supersession chains, more contradictory
  grouping hints, and more artifact-volume pressure than Contoso currently
  produces, so the starter defaults are now trustworthy as rails but not yet
  stress-proven at scale.
- `Stress test to add now:` Add synthetic non-Contoso decomposition object
  populations that mix shard, candidate, and frontier-slice identities with
  conflicting lineage, closure reasons, and contradiction states, and confirm
  the rail surface stays stable under that noisier object mix.
- `What would count as failure here:` If later prompts need to redefine IDs,
  contradiction semantics, economics, or observer base fields because the Phase
  0 rail surface was too Contoso-shaped, then this prompt did not establish a
  real generic foundation.
- `What downstream prompt would be poisoned if we ignore this:` Prompt 01 would
  start inventing shard semantics locally, and every later prompt would drift
  into incompatible lifecycle or observer language.
- `Did this reveal a new weakness worth promoting into the weakness register?`
  No new weakness class, but it did narrow the earlier rail weakness: the
  shared Phase 0 rail surface now exists, and the remaining risk is scaling and
  stress-proofing it beyond Contoso rather than inventing it.

## Prompt-By-Prompt Review Surfaces

### Prompt 00: Phase 0 Shared Rails

Focus:

- whether IDs, contradiction states, economics, observer payloads, and
  retention rules are generic enough to survive noisier packages

Expected enterprise pressure:

- more object churn
- more contradictory grouping hints
- more pressure on retention/compression

Stress test direction:

- synthetic non-Contoso object populations with conflicting shard lineage,
  supersession, and contradiction states

### Prompt 01: Package Intake Shard Runner

Focus:

- whether shard sizing and intake economics are really generic and bounded

Expected enterprise pressure:

- uneven DLL complexity
- skewed shard cost
- shard partitioning that accidentally splits real dependency structure

Stress test direction:

- synthetic package shapes with a few giant DLLs, many tiny DLLs, and mixed
  density

### Prompt 01 Review

- `What Contoso proves now:` Contoso is sufficient to prove that package input
  can be split deterministically into intake-only shard units with canonical
  shard IDs, economics metadata, and shard-validity observer payloads without
  pulling in merge or deep execution behavior.
- `What enterprise pressure will likely expose:` Enterprise packages will have
  much more uneven DLL complexity than Contoso, so shard width by DLL count
  alone will eventually be too weak. The current runner proves a bounded first
  split, not a final cost-aware split.
- `Stress test to add now:` Add synthetic package shapes with one or two very
  heavy DLLs mixed into otherwise small shards, and verify the shard runner
  still records honest economics pressure and resplit decisions rather than
  pretending the package is uniformly cheap.
- `What would count as failure here:` If later prompts have to reinterpret
  shard IDs, intake economics, or intake-only scope because the runner emitted
  insufficient metadata, then Prompt 01 did not establish a trustworthy shard
  substrate.
- `What downstream prompt would be poisoned if we ignore this:` Prompt 02 would
  emit inventory on top of weak shard boundaries, and Prompt 03 merge would
  inherit Contoso-shaped shards that look cheaper and cleaner than real
  enterprise slices.
- `Did this reveal a new weakness worth promoting into the weakness register?`
  No new weakness class, but it did narrow the decomposition risk: the
  remaining problem is now richer shard emission and later merge semantics, not
  the absence of a bounded intake shard runner.

### Prompt 02: Shard Inventory And Observation Emitter

Focus:

- whether shard artifacts remain reviewable when shard evidence is noisy,
  incomplete, or contradictory

Expected enterprise pressure:

- more ambiguous observations
- more low-confidence noise
- larger contradiction volume

Stress test direction:

- synthetic shard outputs with ambiguity spikes and conflicting observer outputs

### Prompt 02 Review

- `What Contoso proves now:` Contoso is sufficient to prove that intake shards
  can be turned into canonical shard inventory artifacts, contradiction
  summaries, observer summaries, and bounded confidence placeholders without
  requiring merge semantics or raw-log archaeology.
- `What enterprise pressure will likely expose:` Enterprise packages will
  generate much higher ambiguity and contradiction volume than Contoso, so the
  current emitter proves canonical structure but not yet high-noise readability
  under heavy contradiction pressure.
- `Stress test to add now:` Add synthetic shard outputs with conflicting
  observer results, larger contradiction lists, and mixed confidence states, and
  confirm the emitter preserves those surfaces without collapsing them into a
  single optimistic shard summary.
- `What would count as failure here:` If later prompts have to reinterpret or
  rebuild shard inventory because the emitted artifacts are too sparse, too
  lossy, or too Contoso-shaped, then Prompt 02 did not establish a trustworthy
  emission layer.
- `What downstream prompt would be poisoned if we ignore this:` Prompt 03 merge
  would start with overly clean shard truth, making contradiction-preserving
  merge look better than it really is.
- `Did this reveal a new weakness worth promoting into the weakness register?`
  No new weakness class, but it further narrowed the decomposition gap: the
  next missing layer is contradiction-preserving merge and candidate generation,
  not shard artifact emission.

### Prompt 03: Shard Merge Coordinator

Focus:

- whether merge preserves ambiguity instead of prematurely collapsing it

Expected enterprise pressure:

- overlapping candidate structures
- partial duplicate evidence
- merge-order sensitivity

Stress test direction:

- synthetic shard sets whose merge result changes if provenance or
  contradiction handling is weak

### Prompt 03 Review

- `What Contoso proves now:` Contoso is sufficient to prove that canonical
  shard outputs can be merged into explicit candidate structures with stable
  identities, visible contradiction states, preserved supersession metadata, and
  initial frontier candidates without pretending those candidates are already
  trusted truths.
- `What enterprise pressure will likely expose:` Enterprise packages will bring
  far more overlapping hints, duplicate candidate families, and merge-order
  sensitivity than Contoso currently provides, so the merge layer is now
  structurally real but not yet pressure-tested against heavy ambiguity.
- `Stress test to add now:` Add synthetic shard populations where multiple
  shards disagree on labels, member sets, and supersession lineage for the same
  candidate key, and confirm merge keeps those disagreements explicit instead of
  picking a winner silently.
- `What would count as failure here:` If later prompts depend on merge outputs
  that only look coherent because the hint volume was sparse and tidy, then
  Prompt 03 would have created a misleading candidate layer.
- `What downstream prompt would be poisoned if we ignore this:` Prompt 04 and
  Prompt 05 would infer initialization groups and dependency classes from a
  merge layer that already hid its contradictions.
- `Did this reveal a new weakness worth promoting into the weakness register?`
  No new weakness class, but it narrowed the next real gap: higher-order
  inference still needs stronger-than-Contoso ambiguity pressure before we can
  trust these candidates broadly.

### Prompt 04: Cross-DLL Initialization-Group Inference

Focus:

- whether init groups stay bounded and specific

Expected enterprise pressure:

- real state packages spanning many modules
- false positives from semantic similarity
- accidental package-wide blob formation

Stress test direction:

- fixtures or synthetic evidence where multiple plausible init groups exist and
  only one is real

### Prompt 04 Review

- `What Contoso proves now:` Contoso is sufficient to prove that merged
  initialization-group candidates can be refined into bounded cross-DLL state
  packages with explicit exported-state artifacts, downstream consumer hints,
  plausibility observers, and package-wide blob guards.
- `What enterprise pressure will likely expose:` Enterprise systems will have
  more competing partial state packages and more ambiguous downstream consumers
  than Contoso, so the current inference layer proves boundedness and observer
  law, but not yet broad disambiguation under heavy cross-weaving pressure.
- `Stress test to add now:` Add synthetic candidate sets where several plausible
  initialization groups share overlapping member DLLs and exported-state names,
  and verify the system keeps them separate or explicitly tentative instead of
  merging them into a single oversized bootstrap blob.
- `What would count as failure here:` If later prompts inherit initialization
  groups that look specific only because the Contoso hint set was clean, then
  Prompt 04 would be creating brittle state packages instead of reusable
  bounded groups.
- `What downstream prompt would be poisoned if we ignore this:` Prompt 05 and
  Prompt 06 would plan dependency classes and frontier slices on top of
  overconfident initialization groups.
- `Did this reveal a new weakness worth promoting into the weakness register?`
  No new weakness class, but it confirms the next missing pressure point:
  distinguishing broader dependency classes from these bounded state packages.

### Prompt 05: Dependency-Class Inference

Focus:

- whether dependency classes remain distinct from init groups and clusters

Expected enterprise pressure:

- broad shared entity families
- weak evidence for true dependency edges
- temptation to over-group

Stress test direction:

- evidence sets where init-group and dependency-class candidates look similar
  but should resolve differently

### Prompt 05 Review

- `What Contoso proves now:` Contoso is sufficient to prove that merged
  dependency-class candidates can be refined into reusable planning objects
  with explicit dependency kinds, member clusters, member init groups,
  evidence-edge provenance, plausibility observers, and hard failure modes when
  a supposed dependency class is only an init package or only a cluster in
  disguise.
- `What enterprise pressure will likely expose:` Enterprise systems will create
  much denser overlap between true dependency families, bounded init packages,
  and local semantic clusters than Contoso does today, so the current layer now
  proves separation mechanics but not yet heavy ambiguity under many
  same-looking cross-DLL families.
- `Stress test to add now:` Add synthetic candidate sets where several
  dependency-class candidates share overlapping DLL sets, partial evidence-edge
  overlap, and partially matching init-group memberships, and verify the system
  keeps them distinct or explicitly tentative instead of silently broadening
  them into one vague family.
- `What would count as failure here:` If later prompts can only produce useful
  frontier slices because the dependency classes were clean and sparse in
  Contoso, then Prompt 05 would have created a planning primitive that is too
  weak for noisier enterprise packages.
- `What downstream prompt would be poisoned if we ignore this:` Prompt 06 would
  plan slices on top of dependency classes that still hide whether they are
  genuinely broader-than-init-group relationships or just relabeled local
  structure.
- `Did this reveal a new weakness worth promoting into the weakness register?`
  No new weakness class, but it narrowed the remaining gap again: the next
  architectural seam is package frontier slicing that can consume clusters,
  init groups, and dependency classes together without collapsing back into
  DLL-first planning.

### Prompt 06: Package Frontier Slice Planner

Focus:

- whether slices are truly narrow and attributable rather than just renamed DLL
  groups

Expected enterprise pressure:

- more imported truth
- more possible frontiers
- higher cost if slice boundedness is weak

Stress test direction:

- planner inputs with many plausible slices and only a few economically honest
  choices

### Prompt 06 Review

- `What Contoso proves now:` Contoso is sufficient to prove that the
  decomposition outputs can now be turned into bounded package frontier slices
  with explicit imported lower-floor truth, explicit active DLLs, required
  clusters, required init groups, related dependency classes, boundedness
  observers, and machine-readable deferral when broader dependency expansion
  would violate slice economics.
- `What enterprise pressure will likely expose:` Enterprise systems will create
  many more plausible overlapping slices than Contoso, so the current planner
  now proves slice boundedness and explicit deferral, but not yet high-density
  competition among several nearly-valid active slices that all look
  economically tempting.
- `Stress test to add now:` Add synthetic planner inputs with several frontier
  candidates competing for the same init groups and dependency classes, plus
  many more inactive DLLs, and verify the planner keeps imported truth explicit
  and chooses only bounded slices instead of broadening them into
  package-shaped “just this once” work.
- `What would count as failure here:` If later prompts can only execute slices
  coherently because the frontier candidate set was sparse and Contoso-friendly,
  then Prompt 06 would have produced a slice planner that is still too close to
  DLL-first planning under real enterprise pressure.
- `What downstream prompt would be poisoned if we ignore this:` Prompt 07 would
  inherit slices that look attributable only because they never had to compete
  with harder, denser planning choices.
- `Did this reveal a new weakness worth promoting into the weakness register?`
  No new weakness class, but it narrowed the remaining gap again: the next seam
  is execution coordination that preserves these bounded slice semantics at
  runtime instead of collapsing them back into DLL jobs.

### Prompt 07: Slice Execution Coordinator

Focus:

- whether slices survive execution mapping without collapsing back into
  DLL-first behavior

Expected enterprise pressure:

- more lane contention
- more pressure to parallelize too early
- more opportunities for slice attribution to get lost

Stress test direction:

- synthetic multi-slice mapping cases where serialized execution still has to
  preserve narrow attribution

### Prompt 07 Review

- `What Contoso proves now:` Contoso is sufficient to prove that bounded
  frontier slices can be mapped into serialized execution units with explicit
  source-slice attribution, protected imported-truth IDs, required init groups,
  related dependency classes, lane metadata, runtime overrides, and explicit
  refusal of unsafe live parallelism.
- `What enterprise pressure will likely expose:` Enterprise systems will create
  more slices, more contention for the same lane, and more pressure to enable
  concurrency prematurely, so the current coordinator proves that slice context
  can survive execution mapping, but not yet how the system should prioritize
  among many competing bounded slices under heavier runtime pressure.
- `Stress test to add now:` Add synthetic multi-slice plans where several
  slices share some imported-truth dependencies and require strict serialized
  ordering, and verify the coordinator preserves attribution and lane safety
  without flattening those slices into one broad DLL queue.
- `What would count as failure here:` If later prompts only look coherent
  because Contoso execution mapping stayed small and tidy, then Prompt 07 would
  be masking the point where bounded slice planning collapses back into generic
  DLL scheduling.
- `What downstream prompt would be poisoned if we ignore this:` Prompt 08 would
  report clean decomposition state while execution reality was already losing
  slice attribution.
- `Did this reveal a new weakness worth promoting into the weakness register?`
  No new weakness class, but it narrowed the remaining gap again: the next seam
  is observability that can show humans and agents this full decomposition
  state without turning the new artifact set into unreadable clutter.

### Prompt 08: Decomposition Observability And Inspection Surface

Focus:

- whether humans and agents can still inspect the system once artifact volume
  rises

Expected enterprise pressure:

- summary overload
- contradiction hotspot overload
- dashboards that drift away from canonical truth

Stress test direction:

- inspection scenarios with much larger shard and merge volumes than Contoso

### Prompt 08 Review

- `What Contoso proves now:` Contoso is sufficient to prove that the full
  decomposition stack can now be summarized into a bounded inspection surface
  with dashboard counts, imported-to-active ratio, contradiction hotspots,
  observer verdict summaries, per-slice inspection rows, explicit canonical
  source links, and retention-policy classification that keeps the dashboard
  and hotspot reports summary-only.
- `What enterprise pressure will likely expose:` Enterprise systems will
  generate far more slices, contradictions, and intermediate candidates than
  Contoso, so the current layer proves summary-versus-canonical discipline and
  basic readability, but not yet how well the inspection surface compresses
  very high-volume ambiguity without hiding the most important hotspots.
- `Stress test to add now:` Add synthetic decomposition stacks with many more
  shards, several overlapping slices, and much larger contradiction registries,
  and verify the dashboard still highlights the right hotspots and imported
  truth ratio without becoming a second unbounded artifact pile.
- `What would count as failure here:` If later proofs rely on the dashboard
  because the canonical artifact set has become too big to inspect, or if the
  dashboard starts inventing conclusions not traceable to canonical sources,
  then Prompt 08 would have created a shadow source of truth instead of a safe
  inspection layer.
- `What downstream prompt would be poisoned if we ignore this:` Prompt 09 would
  appear cleaner than it really is because the integration proof would be read
  through a lossy or overly optimistic observability layer.
- `Did this reveal a new weakness worth promoting into the weakness register?`
  No new weakness class, but it narrowed the remaining gap again: the next seam
  is the reduced integration proof itself, where we need to confirm these
  systems work together as one honest decomposition layer rather than as a set
  of individually green pieces.

### Prompt 09: Reduced Package Decomposition Proof

Focus:

- whether the full decomposition layer remains honest outside the most familiar
  proving shape

Expected enterprise pressure:

- weaker assumptions about package topology
- more mixed-quality evidence
- broader mismatch between imported truth and active frontier

Stress test direction:

- one reduced proof that is still fixture-safe but intentionally more irregular
  than the standard Contoso package shape

### Prompt 09 Review

- `What Contoso proves now:` Contoso is sufficient to prove one honest reduced
  package decomposition run end to end: the shared rails are used, shard intake
  stays inside the cheap-pass contract, merge keeps contradiction structure,
  initialization groups and dependency classes remain distinct, frontier slices
  stay bounded, execution remains serialized and lane-safe, and the inspection
  layer links back to canonical truth instead of replacing it.
- `What enterprise pressure will likely expose:` Enterprise systems will still
  pressure the decomposition stack much harder than this reduced proof did,
  especially with denser contradictory candidates, more competing slices,
  uneven shard cost, and more realistic runtime contention, so this proof
  establishes coherence but not broad stress-readiness.
- `Stress test to add now:` Add one harder-than-Contoso decomposition proof
  shape with more shards, more overlapping dependency families, and at least a
  few contradictory merge candidates, and confirm the proof still passes
  boundedness and observability gates without manual interpretation.
- `What would count as failure here:` If the architecture only works as one
  coherent stack on this tidy reduced Contoso shape, then Prompt 09 would have
  proven local integration but not real scalability readiness.
- `What downstream prompt would be poisoned if we ignore this:` The next prompt
  written from the strongest blocker would start from false confidence about
  large-package readiness instead of from the narrower remaining stress gap.
- `Did this reveal a new weakness worth promoting into the weakness register?`
  No new weakness class, but it tightened the next real concern: the remaining
  bottleneck is no longer missing decomposition architecture, it is broader
  stress-proofing beyond Contoso and deeper runtime adoption of these new
  planning surfaces.

## What We Should Watch For

The biggest risk is not that Contoso tells us nothing.

The biggest risk is that Contoso tells us something true locally while hiding
what will break at broader scale.

So after each prompt we should ask:

- did this system only work because Contoso is tidy?
- did this system assume less contradiction than a real enterprise package will contain?
- did this system assume cleaner initialization structure than real software will provide?
- did this system stay inspectable when evidence volume went up?
- did this system remain generic, or did it quietly become Contoso-shaped?

## Exit Condition For This Document

This document remains active until both are true:

- the decomposition layer has a successful reduced proof
- at least one harder-than-Contoso stress shape has been run against the
  relevant systems and reviewed here

At that point, the next document should be more specific:

- enterprise expansion candidates
- harder fixture families
- pilot-transfer risks for non-Contoso domains

## Post-Decomposition Hardening Review

### Reduced Batch B Decomposition Run Review

- `What Contoso proves now:` The first real decomposition-native reduced Batch
  B run proved that the new runtime bridge can drive a live campaign from
  decomposition surfaces instead of from `package_frontier_plan` alone. The
  run stayed narrow on the intended three-DLL frontier
  (`contoso_config.dll`, `contoso_reporting.dll`, `contoso_pricing.dll`),
  preserved five DLLs as imported lower-floor truth, emitted
  decomposition-native campaign truth and cohesion fields, and carried slice
  execution attribution through to the three live frontier child rows.
- `What enterprise pressure will likely expose:` Enterprise packages will
  punish the current bridge shape much harder because the runtime still
  collapses multi-slice membership into one per-DLL runtime override. On the
  live reduced run, three active frontier slice IDs were emitted, but all three
  live DLL rows ended up attributed to the same slice after the bridge keyed
  runtime settings by DLL and overwrote earlier slice memberships. Enterprise
  packages with more genuinely distinct slices will make that collapse much
  more dangerous.
- `Stress test to add now:` Add a synthetic or medium-scale proof where two or
  more plausible slices share some DLLs but not the same full target set, and
  require the runtime bridge either to deduplicate those slices into one
  canonical slice explicitly or to preserve separate slice identity all the way
  into campaign truth and child-job attribution.
- `What else broke earlier rather than later:` The reduced run also exposed
  that the active frontier ledger rows were present but not collector-complete:
  the latest rows for the three live child jobs were missing `valid_run`,
  `contract_valid`, strict capture paths, and other strict-audit fields. That
  is useful because it tells us now that the decomposition-native runtime path
  is ahead of the strict collector path.
- `What would count as failure here:` If future reduced or enterprise-style
  runs continue to say `decomposition_plan_present = true` while collapsing
  slice attribution to a last-writer per-DLL override, or if package-floor
  confirmation claims continue to outpace strict ledger validity, then the
  runtime adoption tranche would look more mature than it really is.
- `What downstream prompt would be poisoned if we ignore this:` Any next prompt
  that jumps straight to broader enterprise proving or a larger live Batch B
  confirmation run would inherit false confidence about both slice identity and
  measurement completeness.
- `Did this reveal a new weakness worth promoting into the weakness register?`
  Yes. The reduced live run narrowed the next blocker to a specific runtime and
  capture seam: slice attribution still collapses in the bridge, and strict
  ledger validity is not yet complete for decomposition-native live campaigns.

### Prompt 23 Review: Package-Floor Live Validity And Replay Gate

- `Owner surfaces:` The package-floor validity rule is now owned by
  `api/pipeline/core/package_floor_validity.py` and exercised by
  `scripts/runs/run_package_floor_validity_gate.py`.
- `What this proved:` Reduced Batch B now has a contract-bearing package-floor
  validity gate instead of prompt-memory policy:
  - canonical entry surface is `upload`
  - accepted live origins are `temp_upload` and `bridge_cache`
  - active frontier jobs must be fresh and distinct from baseline and imported
    lower-floor source job ids
- `Bounded live proof:` The reduced Batch B live rerun on campaign `46fe7b2f`
  passed the new gate from artifact evidence, not operator inference:
  - `package_floor_evidence_class = overlap_comparable_confirmation`
  - `valid_for_package_floor_claim = true`
  - `valid_for_comparable_policy = true`
- `What this means now:` Package-floor validity and replay ambiguity are no
  longer the top blocker. The next honest move is the strongest remaining
  trusted frontier loss itself.
- `Next blocker from this result:` `contoso_config.dll` environment-gating is
  now the first bounded frontier repair target, with
  `contoso_reporting.dll` second after that.
