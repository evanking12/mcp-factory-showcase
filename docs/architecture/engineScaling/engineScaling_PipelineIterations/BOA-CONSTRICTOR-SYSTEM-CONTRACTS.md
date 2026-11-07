# Boa Constrictor System Contracts

## Why This Document Exists

The boa-constrictor architecture is now strong enough that its next systems
should stop living in:

- prompt memory
- informal conversation
- re-derived implementation plans

and start living in:

- compact contract-bearing system specs

This document is the implementation anchor for the systems implied by
`BOA-CONSTRICTOR-PACKAGE-DECOMPOSITION.md`.

Its purpose is to define:

- what each system is
- what layer owns it
- what it consumes
- what it emits
- how it communicates with adjacent systems
- how it is verified
- what agents should be able to inspect
- what risks or overfitting concerns it carries

This document should be the reference point for future implementation prompts.

---

## Shared Contract Rules

All systems in this document should follow these repo-level design rules:

### Contract Rule 1: Emit machine-readable artifacts

If a system becomes decision-bearing for expensive package work, it must leave
behind reusable artifacts rather than only logs or prompt-local summaries.

### Contract Rule 2: Reuse existing validation anchors

These systems should integrate with:

- `api/pipeline/core/handoff_contract.py`
- `scripts/harness_lib/collector.py`
- `api/pipeline/core/floor_iteration.py`
- `api/analysis/cohesion.py`
- `sessions/ledger/run_ledger.jsonl`

### Contract Rule 3: Preserve provenance

Every grouping, merge, or recommendation should retain:

- source run or shard
- source evidence
- confidence
- unresolved contradictions

### Contract Rule 4: Be inspectable by humans and agents

Each system should expose enough structure that:

- a human can understand the current decomposition state
- a narrow analysis agent can inspect a bounded subsystem without rebuilding
  full package context

### Contract Rule 5: Start generic

No system in this document should rely on:

- fixture-specific identifiers
- domain hardcoding
- package-family-specific assumptions in core logic

Specificity should live in evidence artifacts, not in generic engine code.

### Contract Rule 6: Every system object needs identity and lifecycle

Every new decomposition object must define:

- stable ID
- source lineage
- supersedes behavior
- contradiction state
- closure / retirement state

This applies to:

- shards
- merged cluster candidates
- initialization-group candidates
- dependency-class candidates
- frontier slices

### Contract Rule 7: Cheap must be measurable

Any system described as:

- cheap
- intake
- broad-first

must define explicit economic limits such as:

- shard width
- runtime budget
- token/tool budget
- escalation threshold

### Contract Rule 8: Observer law comes before expensive decisions

No new decomposition system should become decision-bearing for expensive
package work until it has an explicit observer or verification rule that is
machine-readable and reusable.

### Contract Rule 9: Contradictions must remain visible

Merge and grouping systems must not silently resolve contradictions.
They must preserve explicit contradiction states and provenance.

### Contract Rule 10: Inspection surfaces must summarize, not replace truth

Any dashboard or inspection system should expose underlying truth artifacts.
It must not become a shadow source of truth detached from the real artifacts.

---

## Phase 0 Contract Rails

Before implementing the systems below in full, the repo should define these
cross-system rails:

### Rail 1: Identity And Lifecycle Schema

Purpose:

- provide common lifecycle semantics for all new decomposition objects

Outputs / Artifacts:

- object ID schema
- supersedes schema
- contradiction-state schema
- closure-state schema

Verification / Observer Rule:

- every later system object serializes and round-trips through the common
  lifecycle schema

Why:

- later merge and comparison will be incoherent without this

Provisional default fields:

- `id`
- `object_type`
- `package_id`
- `graph_epoch`
- `source_ids`
- `supersedes_id`
- `supersedes_reason`
- `contradiction_state`
- `active`
- `closed_at`
- `closure_reason`

Provisional default ID formats:

- shard: `shard::<package_id>::<graph_epoch>::<ordinal>`
- cluster candidate: `cluster_candidate::<package_id>::<stable_hash>`
- init-group candidate: `init_group_candidate::<package_id>::<stable_hash>`
- dependency class: `dependency_class::<package_id>::<stable_hash>`
- frontier slice: `frontier_slice::<package_id>::<graph_epoch>::<ordinal>`

Provisional contradiction states:

- `none`
- `tentative`
- `blocked`
- `contradicted`
- `quarantined`
- `superseded`
- `confirmed`

Provisional closure reasons:

- `merged_forward`
- `replaced_by_higher_confidence`
- `invalidated_by_contradiction`
- `retired_as_noise`
- `promoted_to_verified_structure`

### Rail 2: Intake Economics Schema

Purpose:

- make "cheap intake" a measurable constraint rather than an aspiration

Outputs / Artifacts:

- shard width policy
- shard runtime budget
- shard token/tool budget
- escalation thresholds

Verification / Observer Rule:

- intake runs expose whether they stayed inside the cheap-pass contract

Why:

- economics are part of the architecture, not an optional tuning detail

Provisional default values:

- target shard width: `10 DLLs`
- hard split threshold: `15 DLLs`
- target shard runtime budget: `12 minutes`
- hard shard runtime ceiling: `20 minutes`
- target deep-follow-up budget inside intake: `0`
- default shard mode: `intake_only`

Provisional required fields:

- `target_shard_width`
- `actual_shard_width`
- `target_runtime_budget_minutes`
- `actual_runtime_minutes`
- `hard_runtime_ceiling_minutes`
- `budget_breached`
- `intake_mode`

### Rail 3: Observer Vocabulary For Decomposition

Purpose:

- define the expected-versus-observed checks for the new systems

Outputs / Artifacts:

- shard validity observer
- merge coherence observer
- initialization-group plausibility observer
- dependency-class plausibility observer
- frontier-slice boundedness observer

Verification / Observer Rule:

- these observers must exist before the corresponding systems become
  decision-bearing

Why:

- this is the same discipline that already protects stage and package-floor
  work

Provisional payload shape for shard-validity observer:

- `observer_name`
- `object_id`
- `status`
- `capture_valid`
- `runtime_budget_ok`
- `required_artifacts_present`
- `hidden_variable_state_recorded`
- `reasons`
- `warnings`

Provisional payload shape for merge-coherence observer:

- `observer_name`
- `object_id`
- `status`
- `provenance_complete`
- `stable_identity_present`
- `contradictions_visible`
- `ambiguity_score`
- `warnings`

Provisional payload shape for frontier-slice boundedness observer:

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

### Rail 4: Artifact Retention And Compression Policy

Purpose:

- keep the decomposition layer reviewable at scale

Outputs / Artifacts:

- canonical artifact list
- summary-versus-detail policy
- retention windows or cleanup policy

Verification / Observer Rule:

- the decomposition dashboard and collector surfaces can still present a usable
  bounded view at growing package sizes

Why:

- otherwise the architecture will produce too much structure to understand

Provisional default retention policy:

- canonical:
  - shard identity
  - shard summary
  - candidate clusters
  - candidate init groups
  - candidate dependency classes
  - frontier slices
  - observer summaries
- summary-only:
  - raw shard note aggregation
  - intermediate merge traces
  - temporary scoring detail
- superseded or compacted:
  - prior candidate versions with `supersedes_id`
  - redundant merge attempts
  - detail traces already represented in canonical summaries

---

## System 1: Package Intake Shard Runner

### System Name

Package Intake Shard Runner

### Primary Home / Owning Layer

- `api/pipeline/core/`
- package-planning layer above the per-DLL worker pipeline

### Purpose

Run broad, cheap intake passes over bounded DLL shards to collect the minimum
structural evidence needed before deep expensive execution.

### Inputs

- package inventory
- shard membership definition
- package context
- baseline contract if available
- low-cost runtime profile

### Outputs / Artifacts

- shard identity artifact
- shard inventory artifact
- shard observer summary
- shard context artifact
- shard intake summary

Suggested artifact names:

- `package-intake-shard.json`
- `package-intake-observer.json`
- `package-intake-summary.json`

Provisional required fields:

- `id`
- `package_id`
- `graph_epoch`
- `dll_ids`
- `dll_count`
- `intake_mode`
- `runtime_budget`
- `observed_runtime`
- `budget_breached`
- `observer_summary_id`

### Adjacent Systems Touched

- collector / strict audit
- run ledger
- package-floor runtime normalization
- campaign/session capture
- later shard merge coordinator

### Verification / Observer Rule

The shard is valid only if:

- capture is valid
- required shard artifacts are present
- hidden-variable state is recorded
- shard runtime profile matches the intended cheap-intake mode
- shard stayed within the intake economics contract

### Measurable Success Effect

- package receives broad structure cheaply
- expensive worker runs are delayed until a better split exists
- first-run planning quality improves

### Monitoring Surface

- shard count
- DLLs per shard
- shard validity rate
- average shard runtime cost
- number of candidate structures emitted per shard
- shard budget breach count

### Strengths

- creates a real first-run organizational layer
- keeps the first pass cheap
- gives later systems structured raw material to merge

### Weaknesses / Overfitting Risks

- can devolve into shallow noise if the profile is too weak
- can become expensive if shard passes accidentally do deep work
- easy to overfit shard heuristics to the fixture suite

### Why Those Weaknesses Matter

If shard intake is noisy, then everything above it becomes noisier:

- merge
- dependency grouping
- frontier planning
- agent work slices

### Explicit Do-Not-Use-When / Scope Boundary

Do not use this as the deep execution system.
Its job is to collect structure, not to prove final behavior across the shard.
Do not run this as a "cheap pass" if the runtime profile routinely breaches the
intake economics contract.

### Analysis-Agent Usability

Narrow analysis agents should be able to inspect one shard and answer:

- what DLLs were in it?
- what structural clues emerged?
- what likely groups were detected?
- what was too weak to trust?

---

## System 2: Shard Inventory And Observation Emitter

### System Name

Shard Inventory And Observation Emitter

### Primary Home / Owning Layer

- package intake artifact layer

### Purpose

Normalize what each shard observed into a stable, comparable artifact set that
later merge logic can consume without raw-log archaeology.

### Inputs

- shard run output
- discovery metadata
- package context
- cheap observer outputs

### Outputs / Artifacts

- candidate DLL roles
- candidate family membership
- read-safe surface hints
- producer/consumer hints
- environment and initialization hints
- contradiction and confidence summary

Suggested artifact names:

- `shard-inventory.json`
- `shard-observations.json`
- `shard-contradictions.json`

Provisional required fields:

- `shard_id`
- `observations`
- `candidate_roles`
- `candidate_family_membership`
- `candidate_init_hints`
- `candidate_dependency_hints`
- `confidence_summary`
- `contradiction_state`

### Adjacent Systems Touched

- collector
- run ledger
- future merge coordinator
- package intake shard runner

### Verification / Observer Rule

The emitted structure is acceptable only if:

- every observation retains provenance
- confidence is explicit
- contradictions are not silently collapsed away
- stable IDs or identity references are preserved where applicable

### Measurable Success Effect

- later merge logic can consume structured shard output directly
- fewer manual interpretation steps are required

### Monitoring Surface

- observation count by type
- contradiction count
- confidence distribution
- unresolved ambiguity count
- unlabeled or identity-weak observation count

### Strengths

- turns cheap runs into reusable structure
- supports later merge and audit

### Weaknesses / Overfitting Risks

- too many weak observation types can make merge harder
- labels can drift without stable IDs

### Why Those Weaknesses Matter

This emitter becomes the language that the merge system reads.
If the language is weak, the merge is weak.

### Explicit Do-Not-Use-When / Scope Boundary

Do not let this emitter decide package frontier policy directly.
It reports structure; it does not choose the next expensive slice on its own.

### Analysis-Agent Usability

Agents should be able to inspect one shard’s observations and summarize:

- most likely cluster candidates
- most likely initialization hints
- most important contradictions

---

## System 3: Shard Merge Coordinator

### System Name

Shard Merge Coordinator

### Primary Home / Owning Layer

- `api/pipeline/core/`
- package decomposition layer

### Purpose

Merge many cheap shard outputs into candidate package structure without forcing
false certainty.

### Inputs

- shard identity artifacts
- shard inventory artifacts
- shard observation artifacts
- prior package truth
- prior known cluster or initialization-group truth

### Outputs / Artifacts

- merged candidate clusters
- merged candidate initialization groups
- merged candidate dependency classes
- merged imported-truth candidates
- merged active-frontier candidates
- merge confidence and contradiction registry

Suggested artifact names:

- `shard-merge-summary.json`
- `candidate-clusters.json`
- `candidate-init-groups.json`
- `candidate-dependency-classes.json`

Provisional required fields:

- `id`
- `source_shard_ids`
- `merged_object_ids`
- `confidence`
- `contradiction_state`
- `ambiguity_score`
- `supersedes_id`

### Adjacent Systems Touched

- package intake shard runner
- shard observation emitter
- cluster/prerequisite-state structures
- package frontier slice planner
- package truth/cohesion

### Verification / Observer Rule

Merge is valid only if:

- merged objects retain provenance
- confidence is explicit
- contradictions remain visible
- stable identity exists for merged objects
- supersession and closure semantics are preserved

### Measurable Success Effect

- the package is no longer a flat DLL list
- later expensive runs are chosen from merged structure, not manual intuition

### Monitoring Surface

- cluster candidate count
- initialization-group candidate count
- dependency-class candidate count
- merge ambiguity count
- merge contradiction count
- superseded-object count

### Strengths

- turns many cheap shards into actionable structure
- gives package planning a real substrate

### Weaknesses / Overfitting Risks

- false merges can poison expensive work
- premature collapse of ambiguity creates fake confidence
- arbitrary shard boundaries can leak into merge logic

### Why Those Weaknesses Matter

This system shapes later package spending.
Bad merge logic means bad expensive-run choices.

### Explicit Do-Not-Use-When / Scope Boundary

Do not use merge results as final truth.
This system proposes package structure; later floors still need to prove it.

### Analysis-Agent Usability

Agents should be able to inspect one merged object and answer:

- what source shards created it?
- what evidence supports it?
- what ambiguity remains?

---

## System 4: Cross-DLL Initialization-Group Inference

### System Name

Cross-DLL Initialization-Group Inference

### Primary Home / Owning Layer

- package decomposition layer
- adjacent to `prerequisite_state_groups.py`

### Purpose

Infer bounded prerequisite-state packages that may span multiple DLLs and feed
later consumer clusters or frontier slices.

### Inputs

- shard observation artifacts
- merged candidate clusters
- produced handles/tickets/tokens/state outputs
- downstream consumer hints
- existing prerequisite-state groups

### Outputs / Artifacts

- candidate initialization groups
- exported state artifacts
- likely downstream consumers
- confidence and unresolved contradictions

Suggested artifact names:

- `candidate-init-groups.json`
- `init-group-dependency-map.json`

Provisional required fields:

- `id`
- `package_id`
- `source_ids`
- `member_functions`
- `member_dlls`
- `exported_state_artifacts`
- `likely_downstream_consumers`
- `confidence`
- `contradiction_state`

### Adjacent Systems Touched

- prerequisite-state groups
- shard merge coordinator
- dependency-class inference
- package frontier slice planner
- floor iteration

### Verification / Observer Rule

An initialization group is believable only if:

- exported state or prerequisite evidence is explicit
- downstream consumers are identifiable
- group provenance is retained
- the group is bounded enough to avoid collapsing into a package-wide init
  bucket

### Measurable Success Effect

- repeated setup rediscovery decreases
- package runs can reuse cross-DLL bootstrap state more deliberately

### Monitoring Surface

- initialization-group count
- single-DLL versus cross-DLL group ratio
- reused-group rate
- downstream consumer count per group
- oversized-group count

### Strengths

- makes invisible setup structure explicit
- provides the first real answer to cross-weaving state

### Weaknesses / Overfitting Risks

- easy to infer giant vague init groups
- easy to misread overlap as true prerequisite linkage

### Why Those Weaknesses Matter

If initialization groups are sloppy, they do not reduce cost.
They only create more confusing metadata.

### Explicit Do-Not-Use-When / Scope Boundary

Do not use this system to model all semantic relationships.
It is only for prerequisite and exported-state structure.

### Analysis-Agent Usability

Agents should be able to inspect one candidate init group and answer:

- what state does it export?
- who likely consumes it?
- what evidence made the system think this is one group?

---

## System 5: Dependency-Class Inference

### System Name

Dependency-Class Inference

### Primary Home / Owning Layer

- package decomposition layer

### Purpose

Infer reusable cross-DLL relationship categories that explain why different
surfaces need to be reasoned about together.

### Inputs

- shard observations
- merged candidate structures
- shared entity continuity
- shared artifact continuity
- shared state and initialization evidence

### Outputs / Artifacts

- dependency class objects
- participating DLLs
- participating clusters
- participating initialization groups
- edge confidence

Suggested artifact names:

- `candidate-dependency-classes.json`
- `dependency-edge-summary.json`

Provisional required fields:

- `id`
- `package_id`
- `dependency_kind`
- `member_dlls`
- `member_clusters`
- `member_init_groups`
- `evidence_edges`
- `confidence`
- `contradiction_state`

### Adjacent Systems Touched

- shard merge coordinator
- initialization-group inference
- package frontier slice planner
- cross-DLL evidence auditing

### Verification / Observer Rule

A dependency class is valid enough to act on only if:

- it is backed by explicit evidence
- it distinguishes real dependency from mere overlap
- confidence and ambiguity are explicit
- participating structures remain bounded enough to be actionable

### Measurable Success Effect

- package planning shifts from DLL-first to dependency-first
- interwoven work becomes more explainable

### Monitoring Surface

- dependency-class count
- average member count
- cross-DLL edge density
- evidence-backed versus weakly inferred ratio
- oversized or low-specificity class count

### Strengths

- gives cross-DLL planning a generic language
- supports enterprise transfer better than package-specific heuristics

### Weaknesses / Overfitting Risks

- overlap can be mistaken for dependency
- dependency classes can become too broad and lose usefulness

### Why Those Weaknesses Matter

If dependency classes are wrong, the package planner will run the wrong things
together and waste expensive cycles.

### Explicit Do-Not-Use-When / Scope Boundary

Do not treat a dependency class as a frontier slice automatically.
It is a planning primitive, not necessarily the final execution unit.

### Analysis-Agent Usability

Agents should be able to inspect a dependency class and answer:

- what evidence supports it?
- what DLLs or clusters participate?
- what is likely shared versus only tentatively shared?

---

## System 6: Package Frontier Slice Planner

### System Name

Package Frontier Slice Planner

### Primary Home / Owning Layer

- package floor planning layer
- adjacent to `package_frontier_planner.py`

### Purpose

Translate merged package structure into the next bounded active work slices
while freezing imported lower-floor truth.

### Inputs

- merged candidate clusters
- merged initialization groups
- dependency classes
- prior package truth
- baseline contract
- imported lower-floor truth candidates

### Outputs / Artifacts

- active frontier slices
- imported lower-floor set
- deferred set
- slice execution order
- package-floor stop conditions

Suggested artifact names:

- `package-frontier-plan.json`
- `package-frontier-slices.json`
- `imported-lower-floor-set.json`

Provisional required fields:

- `id`
- `package_id`
- `graph_epoch`
- `slice_members`
- `slice_kind`
- `imported_truth_ids`
- `active_work_ids`
- `rationale`
- `confidence`
- `contradiction_state`

### Adjacent Systems Touched

- floor iteration
- package truth/cohesion/attribution
- compare-runs and promotion policy
- runner

### Verification / Observer Rule

A frontier plan is usable only if:

- imported truth is explicit
- active slices are explicit
- slice rationale is explicit
- baseline/comparison boundaries are explicit where required
- active slices are smaller and more attributable than the naive whole-package
  alternative

### Measurable Success Effect

- package runs stop defaulting to “all DLLs live”
- expensive work is focused on a smaller active frontier

### Monitoring Surface

- imported-to-active ratio
- frontier slice count
- average slice size
- frontier shrinkage over iterations
- reopened imported-truth count

### Strengths

- turns decomposition into actual run policy
- directly improves economics

### Weaknesses / Overfitting Risks

- bad slice planning can reopen solved work
- package planning may still be too DLL-shaped if slices are shallow

### Why Those Weaknesses Matter

This is the system that spends runtime budget.
Poor slice planning is expensive immediately.

### Explicit Do-Not-Use-When / Scope Boundary

Do not use this planner when the lower decomposition layers are still too weak
to support honest slice selection.

### Analysis-Agent Usability

Agents should be able to inspect one frontier slice and answer:

- why is it active?
- what imported truths surround it?
- which init groups and dependency classes are relevant?

---

## System 7: Slice Execution Coordinator

### System Name

Slice Execution Coordinator

### Primary Home / Owning Layer

- package orchestration layer
- runner-adjacent

### Purpose

Map frontier slices into the existing worker pipeline without forcing the
pipeline itself to become the decomposition system.

### Inputs

- package frontier plan
- slice definitions
- imported lower-floor truth
- runner/runtime settings

### Outputs / Artifacts

- per-slice execution requests
- per-slice runtime settings
- per-slice capture and observer results

Suggested artifact names:

- `slice-execution-map.json`
- `slice-runtime-overrides.json`
- `slice-outcomes.json`

Provisional required fields:

- `slice_id`
- `runtime_shape`
- `protected_imported_truth_ids`
- `active_target_ids`
- `status`
- `observer_summary_id`

### Adjacent Systems Touched

- runner
- floor iteration
- campaign truth/cohesion
- collector
- ledger

### Verification / Observer Rule

Slice execution is working only if:

- slices remain bounded during execution
- imported truth is not silently reopened
- slice outcomes map cleanly back into package-floor artifacts
- the execution mapping does not collapse back into raw DLL-wide behavior by
  default

### Measurable Success Effect

- the worker pipeline can act on slices rather than raw DLL choices

### Monitoring Surface

- slice execution count
- reopened imported truth count
- slice success/failure localization
- fallback-to-dll-shaped execution count

### Strengths

- lets the existing pipeline stay strong while moving the planning boundary up
- avoids big-bang replacement of the worker engine

### Weaknesses / Overfitting Risks

- can become a thin DLL wrapper if slice definitions are weak
- can inherit too much complexity if runner/runtime boundaries are unclear

### Why Those Weaknesses Matter

This system is where decomposition becomes execution.
If it is shallow, the whole architecture remains “same pipeline, smarter rerun.”

### Explicit Do-Not-Use-When / Scope Boundary

Do not let this coordinator invent new semantic grouping rules.
It should execute slices defined by upstream planning systems.

### Analysis-Agent Usability

Agents should be able to inspect execution maps and answer:

- which slice ran?
- which runtime settings were applied?
- what imported truths were protected?

---

## System 8: Decomposition Observability And Inspection Surface

### System Name

Decomposition Observability And Inspection Surface

### Primary Home / Owning Layer

- package analysis / reporting layer

### Purpose

Give humans and narrow analysis agents a coherent way to look inside the
package decomposition state at every level.

### Inputs

- shard artifacts
- merged candidate structures
- package frontier plans
- slice execution outcomes
- package truth/cohesion

### Outputs / Artifacts

- decomposition dashboard artifact
- merge and ambiguity summaries
- slice-inspection summaries
- agent-facing bounded reports

Suggested artifact names:

- `decomposition-dashboard.json`
- `merge-ambiguity-report.json`
- `slice-inspection-report.json`

Provisional required fields:

- `package_id`
- `graph_epoch`
- `active_slice_ids`
- `imported_truth_ids`
- `ambiguity_hotspots`
- `contradiction_hotspots`
- `bounded_summary`

### Adjacent Systems Touched

- collector
- cohesion
- package truth
- ledger
- analysis-agent tooling

### Verification / Observer Rule

The inspection surface is useful only if:

- it maps back to real artifacts
- it exposes ambiguity explicitly
- it does not hide provenance
- it remains bounded enough for human and agent review

### Measurable Success Effect

- less manual archaeology
- better agent assignment quality
- faster human review of package state

### Monitoring Surface

- ambiguity count
- unproven grouping count
- active slice count
- imported truth count
- inspection payload size / boundedness

### Strengths

- makes the system inspectable
- supports the narrow analysis-agent model directly

### Weaknesses / Overfitting Risks

- can become a reporting swamp if it mirrors everything without hierarchy
- can hide the most important signals under too much status detail

### Why Those Weaknesses Matter

At large scale, observability that is technically complete but cognitively
useless is almost as bad as no observability at all.

### Explicit Do-Not-Use-When / Scope Boundary

Do not let this become the source of truth itself.
It should summarize and expose underlying truth artifacts, not replace them.

### Analysis-Agent Usability

This system is explicitly for agent usability.
It should support questions like:

- what is the current package frontier?
- what init groups are still tentative?
- where is ambiguity concentrated?
- what slice is worth investigating next?

---

## Shared Criteria The Systems Should Offer

Not every system needs every field, but collectively the boa-constrictor
systems should offer these criteria:

- explicit provenance
- explicit confidence
- explicit ambiguity
- stable IDs
- bounded output artifacts
- compatibility-tolerant readers
- package-floor integration
- collector-valid runs
- ledger compatibility
- agent-readable inspection surfaces

These criteria matter because the architecture is being built for:

- long iteration chains
- multiple agents
- expensive package decisions

If these systems cannot be inspected, audited, and compared, they will not be
safe enough to drive product-scale work.

---

## Current Implementation Warnings

If implementation started immediately, the main risks would be:

- observer law still weaker here than in the existing stage and package-floor
  systems
- economics still under-specified for the so-called cheap shard passes
- scheduler still more DLL-shaped than slice-shaped
- contradiction handling still not standardized enough for shard merge
- artifact volume still at risk of outrunning reviewability
- current proving ground still too fixture-shaped to trust any early grouping
  system that silently hardcodes Contoso assumptions

These warnings do not block implementation forever.
They mean Phase 0 rails should be built first and verified before the later
systems become decision-bearing.

### Why This Warning Block Exists

The architecture is now strong enough that the main danger is not lack of
ideas.
The main danger is implementing the right systems in the wrong order.

This means the immediate implementation rule is:

- do not begin with shard merge, dependency classes, or slice scheduling
- begin with the shared rails

The required first implementation tranche is:

- lifecycle schema
- economics schema
- observer vocabulary
- contradiction-state contract
- artifact retention/compression policy

These rails should become the first executable prompt because they are:

- easiest to verify
- most reusable across all later systems
- the main protection against decomposition-layer drift and complexity collapse

### Clarification On Defaults

The provisional values in this document are:

- starter defaults
- safe placeholders from current repo knowledge
- implementation scaffolding

They are not:

- permanent architecture law
- final scale values
- proof that these numbers are already optimal

They exist so implementation can begin with real contract fields instead of
waiting for perfect certainty.

---

## Implementation Order Recommendation

The recommended build order is:

1. Package Intake Shard Runner
2. Shard Inventory And Observation Emitter
3. Shard Merge Coordinator
4. Cross-DLL Initialization-Group Inference
5. Dependency-Class Inference
6. Package Frontier Slice Planner
7. Slice Execution Coordinator
8. Decomposition Observability And Inspection Surface

Why this order:

- it builds from broad cheap intake toward expensive focused execution
- it forces evidence and grouping to exist before scheduling spends money
- it keeps the existing worker pipeline stable while the decomposition layer is
  built above it

---

## Dynamic Resolution Rule During Implementation

These contracts are intentionally strong enough to start implementation, but
they do not pretend to fully solve every later-stage detail in advance.

As each system is implemented, the following details should be resolved
dynamically for that system:

- exact repo file and module ownership
- final canonical JSON schemas for its artifacts
- exact test fixture design
- exact merge or scoring logic where applicable
- exact scheduler behavior where applicable
- exact compare and promotion implications where applicable

### Why This Rule Exists

The earlier systems should teach us what the later systems actually need.

If we try to freeze all of those details before any implementation:

- we will over-speculate
- we will overfit the design to current imagination rather than evidence
- later systems will inherit unnecessary rigidity

### What Every Implementation Prompt Should Require

For the specific system being built, the prompt should force explicit answers
to:

- current purpose
- scope boundary
- exact outputs
- exact observer
- exact downstream trust boundary
- what evidence would justify changing the system’s role later

### Strength

- keeps purpose and contract aligned with real implementation evidence

### Weakness If Ignored

- neighboring systems will drift into each other
- prompt memory will silently redefine system purpose
- cohesion will degrade even if each local system appears individually useful

### Why That Weakness Matters

This architecture only works if systems become more explicit as they are
implemented, not more improvisational.
