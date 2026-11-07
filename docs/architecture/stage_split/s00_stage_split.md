# S-00 Stage Split

> Migration-only doctrine surface.
> This document preserves the recommended `S-00` split intent that existed
> before the latest evidence-led S-00 campaign work. Treat it as design
> baseline and product intent, not as the current implementation plan by
> itself.
> Current implementation truth lives in
> [api/pipeline/README.md](../../../api/pipeline/README.md)
> and the sticky docs under
> [api/pipeline/s00_setup/](../../../api/pipeline/s00_setup).
> `api/pipeline/core/handoff_contract.py` remains transition contract context,
> not broad live stage truth.

## Current Evidence Note

The S-00 migration campaign has now produced stronger evidence than this
original design note had:

- S-00 internal seams exist for calibration/baseline truth, vocab/prior hints,
  static surface extraction, static enrichment, packet production, and
  orchestration.
- `s01_handoff_packet.json` exists, is consumed by S-01, and affects bounded
  S-01 target prioritization.
- `static_enrichment.json` exists as an additive normalized artifact and is
  exposed in hosted saved-session artifacts at both canonical and stage-local
  paths.
- hosted Fast, Required, and Medium01 baselines have stayed green across the
  relevant checkpoints.
- the evidence-led runtime split has promoted three live checkpoint IDs:
  - `s00_setup_baseline`
  - `s00_static_evidence`
  - `s00_admission_handoff`
- `s00_setup` remains a compatibility parent and legacy stage identity.

So any future implementation decision should be based on current campaign
evidence, not on this document alone. The durable intent still stands: split
S-00 only where each proposed stage owns a distinct purpose, artifact, failure
boundary, and handoff obligation.

## Evidence-Led Runtime Result

The implemented runtime-visible split is:

1. `s00_setup_baseline`
2. `s00_static_evidence`
3. `s00_admission_handoff`

This adapts the earlier rough design. The old `static_prior_shaping` idea is
not a separate runtime stage today; its current live responsibility is captured
by normalized static enrichment plus the admission/handoff packet discipline.

The closeout decision is compatibility-preserving:

- keep `s00_setup` as the parent compatibility identity
- keep legacy artifact paths and wrappers
- treat any future removal of `s00_setup` compatibility as a separate cleanup
  campaign requiring explicit approval

## Summary

The front of the live pipeline is more overloaded than the original 7-to-11
split note treated it.

Current `S-00` is not one clean setup stage. It is three different jobs bundled
together:

- sentinel calibration
- vocab seeding
- static analysis and Ghidra-derived enrichment

That compression is now a real bottleneck.

It hurts failure attribution because one front-stage failure can mean:

- setup contract failure
- static extraction weakness
- bad prior shaping

and those are not the same failure.

It also hurts economics because later stages keep paying runtime and probe cost
for static structure that should have been owned earlier and more explicitly.

The recommended split is:

1. `setup_and_contract_baseline`
2. `static_surface_extraction`
3. `static_prior_shaping`

This should be treated as a later bounded migration slice after the main
middle-band split doctrine, not as permission to rewrite the whole front of the
pipeline at once.

## Why A Dedicated `S-00` Split Is Now Justified

The earlier stage-split doctrine in
[7_stages_to_11_stages.md](7_stages_to_11_stages.md)
was directionally right that the middle band was the first obvious overload.
That is still true.

But later archived review notes already identified a second front-loaded
problem:

- live `S-00` bundles environment/setup truth
- static extraction truth
- static prior/plan truth

Those are different train cars.

The live code no longer runs all S-00 work inside `run_s00(ctx)`. The runner
now exposes setup baseline, static evidence, and admission handoff as separate
checkpoint IDs while keeping `run_s00` as the legacy package dispatch surface.

## What The Current Bottleneck Actually Is

The bottleneck is not “`S-00` needs more static information.”

The bottleneck is:

- setup and contract baseline truth are mixed with static extraction
- static extraction is mixed with prior shaping
- some Ghidra-derived surfaces are present, but mostly as piggyback data on
  `invocables`, `static_hints_block`, `call_graph`, or `ghidra_data_types`
- later stages inherit useful static structure without that structure having a
  clean first-class ownership boundary

That creates three recurring failures:

1. **Attribution blur**
- if downstream probe behavior is weak, it is hard to tell whether the problem
  is:
  - bad setup truth
  - weak static surface extraction
  - weak prior shaping

2. **Runtime overpayment**
- later stages spend probe budget discovering callable or prerequisite
  structure that should have been surfaced earlier

3. **Knowledge-landfill risk**
- if this is solved badly, `S-00` becomes a dump of static facts rather than a
  narrow foundation with operationally useful artifacts

The right correction is not “add more static stuff.”
It is “separate extraction from shaping and only promote what reduces later
waste.”

## Relationship To The 11-Stage Target

This split should be read as a front-end refinement that fits the same stage
law used elsewhere in
[stage_purpose.md](stage_purpose.md):

- one dominant purpose
- one primary artifact
- one local failure boundary
- one next diagnostic step

It also fits the later target architecture:

- `N-00 setup`
- `N-01 observational_intake`
- later `surface_inventory`
- later `frontier_ranking`

from
[stage_purpose.md](stage_purpose.md).

The practical interpretation is:

- the current live `S-00` is too overloaded to map cleanly to one future
  target stage
- the front of the pipeline needs its own smaller train cars before the later
  inventory/ranking machinery can stay honest

## Recommended Split

### 1. `setup_and_contract_baseline`

- purpose
  - establish run-local setup truth and the baseline contract the rest of the
    pipeline inherits
- likely owned concerns
  - sentinel calibration
  - run-local setup truth
  - baseline schema or invocable contract snapshot
  - early user-hint merge that belongs to startup truth rather than later
    shaping
- primary artifact family
  - setup baseline packet
  - sentinel calibration packet
- local failure boundary
  - startup, contract, or baseline capture failure
- next diagnostic step
  - inspect setup truth before reasoning about static evidence quality

### 2. `static_surface_extraction`

- purpose
  - extract cheap, reusable static structure from the DLL without making broad
    semantic claims
- likely owned concerns
  - current static analysis core
  - strings and import/capability extraction
  - Ghidra-derived callable and structural packetization
  - current opportunistic call-graph or Ghidra sidecars, if retained
- primary artifact family
  - static surface packet
  - candidate `surface_inventory.json`
- local failure boundary
  - static surface incomplete, unstable, or under-extracted
- next diagnostic step
  - inspect what was actually extracted before letting later stages infer from
    it

### 3. `static_prior_shaping`

- purpose
  - turn extracted static structure into bounded, explicitly non-authoritative
    priors for later stages
- likely owned concerns
  - vocab shaping
  - prerequisite hints
  - frontier-shaping hints
  - explicit deferment or ambiguity notes where justified
- primary artifact family
  - prior-shaping packet
  - candidate `candidate_prerequisite_graph.json`
- local failure boundary
  - priors overfit, under-constrain, or mislead the next stage
- next diagnostic step
  - inspect whether later stages are receiving useful priors rather than raw
    static bulk

## What The GhidraMCP Evaluation Campaign Changed

The evaluation campaign at
ghidra_mcp_static_evaluation_v1
did not justify broad Ghidra expansion.

It did something narrower and more useful:

- it tested which extracted static surfaces actually look strong enough for
  later contract discussion
- it compared those wins against current `S-00` ownership and downstream use
- it forced a utility-oriented judgment rather than “Ghidra can expose this”

The closeout in
EVALUATION-DECISION-PACKET.md
landed on a narrow result:

- `callable_inventory`
  - strong enough for later contract discussion
  - best fit: `static_surface_extraction`
- `xref_prerequisite_hints`
  - strong enough for later contract discussion
  - best fit: `static_prior_shaping`
- `bounded_decompile_snippets`
  - useful, but not yet justified as a first-class artifact
  - defer pending runtime utility proof
- `strings`
  - already materially owned by current `S-00`
  - do not promote again
- `imports`
  - already materially owned by current `S-00`
  - do not promote again
- `datatype_enum_surfaces`
  - not strong enough yet
- `dedicated_ambiguity_surfaces`
  - not strong enough yet

That matters because it prevents the wrong `S-00` split.

The wrong split would be:

- add many new Ghidra artifacts
- widen `S-00`
- call the front-end “richer”

The stronger split is:

- keep the split narrow
- promote only the surfaces that survived comparative evaluation
- leave decompile richness, type richness, and ambiguity richness deferred
  unless a later utility campaign earns them

## Current Recommendation For Future Artifact Ownership

If a later implementation slice is opened, the narrow candidate ownership is:

### `static_surface_extraction`

- likely future first-class artifact:
  - `surface_inventory.json`
- minimum intended contents
  - callable inventory
  - export or method identity
  - parameter names and types as statically observed
  - provenance or trust markers

### `static_prior_shaping`

- likely future first-class artifact:
  - `candidate_prerequisite_graph.json`
- minimum intended contents
  - candidate prerequisite edges
  - evidence kind
  - confidence or provenance markers
  - explicit `non_authoritative: true`

### Explicitly Not Proposed Yet

- a new first-class `decompile_snippets.json`
- a datatype/enum contract
- a dedicated ambiguity contract
- any runtime or unlock truth contract

## Migration Constraints

This document is not permission to jump straight into code changes.

The original pre-migration safety concerns still apply in spirit, although the
specific pre-migration packet is now archived because the campaign has produced
newer evidence:

- freeze the current 7-stage contract as the baseline
- keep compatibility aliases for moved artifacts
- keep lane trust, artifact-root integrity, and proving authority outside the
  stage map
- use bounded migration slices, not broad rewrite energy

Additional `S-00`-specific constraints:

- do not combine the `S-00` split with the full 7->11 migration in one code
  slice
- do not promote every useful GhidraMCP extraction into a first-class contract
- do not duplicate `invocables_map.json` without explicit ownership and reader
  migration
- do not treat static prerequisite hints as authoritative truth

## What Should Be Preserved

- sentinel calibration as a distinct front-stage concern
- current `vocab` and static hint surfaces where they already provide real
  value
- the rule that static evidence is prior, not truth
- the rule that later stages still earn runtime meaning
- the broader 11-stage target and migration discipline already established in
  the existing `stage_split` docs

## What Should Be Constrained Or Deferred

- broad Ghidra expansion
- decompile-richness promotion without utility proof
- datatype and ambiguity contracts
- any claim that the evaluation campaign already justified adoption or runtime
  redesign

## Practical Next Step

The next honest move after this document is not a broad rewrite.

It is one bounded follow-on slice that proves whether the two surviving
contract candidates:

- `surface_inventory.json`
- `candidate_prerequisite_graph.json`

actually reduce later-stage waste enough to justify implementation.

Until that proof exists, the split is architecturally justified as a target,
but still not fully implementation-authorized as a broad front-end rewrite.

## Documentation Shape During Refactor

As `S-00` is split, documentation should be reorganized around the stage
without turning this into a broad `api` cleanup first.

### Directionally Right

- `S-00` benefits from a clearer local doc stack
- a broad stage `README.md` that routes into more specific surfaces is the
  right shape
- stage docs should explicitly cover:
  - purpose
  - owned inputs
  - owned outputs
  - artifact contracts
  - downstream consumers
  - systems in play
  - non-goals

### Risky Or Premature

- reorganizing the whole `api` tree before stage boundaries are settled
- writing many overlapping docs that drift from code
- letting `FLOW.md` describe aspirational behavior while the live entrypoint
  still does something narrower

That last point already exists in live `S-00`: current
[FLOW.md](../../../api/pipeline/s00_setup/FLOW.md)
is broader than the actual live entrypoint in
[__init__.py](../../../api/pipeline/s00_setup/__init__.py).

So the first documentation rule should be:

- separate live contract from target design

### What Should Be Preserved

- the current stage folder structure in `api/pipeline/*`
- the rule that each stage owns its own local docs
- migration doctrine under `docs/architecture/stage_split`

### What Should Be Constrained

- do not turn this into “reorganize all of `api`”
- do not let every stage invent its own doc taxonomy
- do not mix migration doctrine, live implementation truth, and target
  architecture in one file

### Recommended Documentation Stack

Keep the code folders where they are.

Add one pipeline-level doc:

- `api/pipeline/README.md`
  - explains the live stage map
  - explains how to navigate stages
  - links to each stage’s local docs

Normalize each stage to the same small doc set:

- `README.md`
  - human entrypoint
  - what this stage is
  - where to look next
- `PURPOSE.md`
  - one dominant assignment
  - non-goals
- `FLOW.md`
  - execution flow only
- `ARTIFACTS.md`
  - inputs
  - outputs
  - aliases
  - downstream consumers
- `SYSTEMS.md`
  - cross-cutting systems this stage depends on but does not own

For stages under migration, add one explicit live-vs-target separation:

- `LIVE-CONTRACT.md` or `CURRENT.md`
- `TARGET.md`

That prevents “what it does now” and “what we want it to become” from being
mixed together.

### Strong `S-00` Template

For `api/pipeline/s00_setup`, the strongest local doc stack would be:

- `README.md`
  - stage overview and navigation
- `PURPOSE.md`
  - current live purpose
- `FLOW.md`
  - current live flow only
- `ARTIFACTS.md`
  - `sentinel_calibration.json`
  - `vocab.json`
  - `static_analysis.json`
  - optional `call_graph.json`
  - optional `ghidra_data_types.json`
  - real downstream readers
- `SYSTEMS.md`
  - checkpointing
  - prior-run inheritance
  - Ghidra provenance
  - lane or proving systems it depends on but does not own

For target-shape guidance after the split begins:

- add `TARGET-SPLIT.md`
- or point directly back to this document and
  [s00_stage_split.md](s00_stage_split.md)

### Practical Rule

Yes, reorganize the documentation around the stage.

No, do not broadly reorganize the `api` folder yet.

The docs should become clearer before the code tree becomes more ambitious.
That gives the repo a more stable operator surface while the architecture is
still moving.

## Foundational-Layer Ordering For `S-00`

Yes, this split is foundational-layer work.

But it is not “just setup.”

The point of the split is to improve what later stages inherit, not to collect
more static material for its own sake.

The right ordering is still:

1. `setup_and_contract_baseline`
2. `static_surface_extraction`
3. `static_prior_shaping`

### Ordering Criteria

This order follows the stronger stage-ordering law:

- cheapest trustworthy prerequisite first
- strongest dependency second
- broad shaping only after extraction
- runtime spend only after static priors are good enough
- semantic truth only after cheaper structure has been harvested

That means `S-00` must remove cheap uncertainty in the right order instead of
letting later stages discover foundational structure reactively.

### Why `setup_and_contract_baseline` Comes First

It comes first because everything else depends on the run-local baseline being
real:

- sentinel truth
- startup truth
- inherited and user-context truth
- baseline contract truth

If that layer is wrong, later static work is built on unstable footing.

Downstream effect:

- `S-01 unlock` does not have to mix startup uncertainty with unlock logic
- `S-02 probe` does not have to guess whether failures are baseline failures or
  probe failures
- later reconcile and synthesis work inherit a cleaner starting contract

### Why `static_surface_extraction` Comes Second

It comes second because priors should not be shaped before the static surface
is actually known.

This layer should own cheap reusable structure such as:

- callable inventory
- imports and strings
- bounded static structure
- any retained Ghidra-derived packetization that survives comparative
  evaluation

Downstream effect:

- `S-01 unlock` receives better concrete surface knowledge before trying to
  force preconditions
- `S-02 probe` spends less runtime budget discovering basic callable or
  structural facts
- later stages receive inspectable static evidence rather than chat-shaped
  intuition

### Why `static_prior_shaping` Comes Third

It comes third because shaping is interpretation.

Interpretation should come after extraction, not before it.

This layer should turn extracted structure into bounded, explicitly
non-authoritative priors such as:

- vocabulary shaping
- prerequisite hints
- frontier-shaping hints

Downstream effect:

- `S-02 probe` gets better sequencing and prerequisite guidance
- later reconcile and synthesis stages inherit shaped priors instead of raw
  static bulk
- runtime stages still own truth closure, because static prior is not runtime
  proof

### Practical Interpretation

This does not change the split count.

It stays:

- `setup_and_contract_baseline`
- `static_surface_extraction`
- `static_prior_shaping`

What the evaluation campaign changed was artifact ambition inside those train
cars, not the number of train cars themselves.

So the ordering is still about:

- dependency
- economics
- failure attribution

not aesthetics, and not a reason to reopen broad stage expansion.

## Handoff Sufficiency For The `S-00` Split

Yes, the `S-00` split needs explicit move-forward criteria.

Each substage must decide whether it has enough trustworthy information to let
the next substage or downstream stage proceed.

### `setup_and_contract_baseline`

- advance if:
  - baseline truth is coherent enough for static work
  - startup, inherited, and user-context truth are not contradictory
- stay or fail if:
  - setup truth is missing
  - startup truth is contradictory
  - the baseline contract is not trustworthy enough to support extraction

Downstream consequence:

- `S-01 unlock` should inherit baseline truth instead of discovering startup
  ambiguity itself
- `S-02 probe` should not have to guess whether failures are setup failures or
  probe failures

### `static_surface_extraction`

- advance if:
  - the static packet is credible enough for shaping
  - extracted surfaces are inspectable and not obviously too thin or unstable
- stay or fail if:
  - extraction is too sparse
  - extraction is too noisy
  - extraction is too unstable to support shaping honestly

Downstream consequence:

- `S-01 unlock` should inherit usable static context rather than discovering
  basic callable structure reactively
- `S-02 probe` should spend runtime budget on real uncertainty instead of basic
  surface discovery

### `static_prior_shaping`

- advance if:
  - priors are bounded and useful
  - they sharpen downstream work without pretending to be truth
- stay or fail if:
  - shaping is overfit
  - shaping is too weak to be useful
  - shaping is indistinguishable from raw static clutter

Downstream consequence:

- `S-02 probe` should inherit enough structure and prerequisite guidance to
  focus on runtime uncertainty
- later reconcile and synthesis stages should inherit cleaner inputs and do less
  rescue work

### Practical Rule

This does not change the split count.

It is still:

- `setup_and_contract_baseline`
- `static_surface_extraction`
- `static_prior_shaping`

The point of this doctrine is to make those three substages more honest about:

- when to advance
- when to stay
- when to fail
- what uncertainty is legal to defer

Static evidence remains prior, not truth, so handoff sufficiency here means
“enough trustworthy information for the next stage’s job,” not semantic
closure.

## Handoff Packet Shape For The `S-00` Split

Yes, `S-00` will produce a lot of information.

No, that should not flow straight into `S-01`.

If raw `S-00` richness is thrown directly into the next stage, the next stage
will drown and turn into an archaeology stage instead of an execution stage.

So `S-00` must emit an organized handoff packet.

### Local `S-00` Example Packet

- `baseline_truth`
  - sentinels
  - startup/setup truth
- `surface_inventory`
  - callable inventory
  - key static surfaces
- `prior_hints`
  - prerequisite hints
  - vocabulary hints
- `deferred_static`
  - extra strings/imports/decompile richness not needed immediately
- `ambiguity_register`
  - where static evidence is thin or uncertain
- `s01_targets`
  - what unlock should actively care about next
- `review_verdict`
  - whether `S-00` met its own handoff contract
- `coordination_decision`
  - the coordinator-owned admission and flow decision for `S-00 -> S-01`
  - should organize:
    - which parts of `baseline_truth` are active for `S-01`
    - which parts of `surface_inventory` are admitted forward now
    - which `prior_hints` are strong enough to carry
    - which `deferred_static` items remain parked
    - whether any parked items must be revived for unlock
    - how `s01_targets` are narrowed so unlock does not drown

### Why This Matters

This does not add a fourth `S-00` substage.

It changes the handoff authority and packet discipline, not the stage count.

The point is:

- `S-00` should not emit “a lot of information”
- `S-00` should emit organized findings for the next stage

That keeps:

- `S-01` focused on unlock and preconditions
- `S-02` focused on real runtime uncertainty
- later reconcile and synthesis stages from inheriting a flood of unshaped
  static material

Static evidence is still prior, not truth, so this packet shape is for
organized handoff and flow control, not semantic closure.

The coordinator here is not a semantic truth owner.
It is the admission organizer for the `S-00 -> S-01` boundary.
That means the stage still does first-pass organization, while the coordinator
decides what narrowed slice actually crosses the boundary.
See the [regression ladder](../testing_strategy/REGRESSION-LADDER.md) for the test layers and their purpose.
![alt text](image-1.png)
