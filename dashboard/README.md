# Pipeline Dashboard

> Specialist cockpit contract.
> This is not the repo `operator_start_here` surface.
> The canonical operator front door is [SETUP.md](../SETUP.md).

The dashboard on `:8082` should convert pipeline state and emitted artifacts
into ranked operator decisions.

This document is the canonical v1 cockpit spec for the dashboard surface on
`:8082`.

The compact pipeline view is available at:

- `http://127.0.0.1:8082/simple`

Primary implementation home:

- [main.py](main.py)

Related startup wiring:

- [start.ps1](../start.ps1)

Startup contract:

- `start.ps1` should reuse healthy MCP Factory listeners already bound to the
  expected ports
- `start.ps1` should stop immediately on foreign port conflicts instead of
  opening duplicate dead service windows
- if the dashboard is up but the pipeline is dropping connections, the cockpit
  should stay in recovery mode and surface graceful `502` responses rather than
  proxy tracebacks

Current operator layout contract:

- the dashboard is the primary cockpit surface after operator startup
- the cockpit must distinguish `chain step` from `pipeline stage`
- left-rail setup utilities should stay compact and collapsible
- `Recent Jobs` should behave like a searchable selector rather than a long
  scrolling utility list
- `Package Intake` is temporary wording over the current `analyze-path` hook and
  exists to bridge today’s entry surface to the intended enterprise package
  workflow
- `Lab Control` is a recovery utility, not a primary decision panel
- `Lab Control` and `Package Intake` should default collapsed in the rail so
  persistent context stays visually dominant
- main screen space should prioritize investigation, tiered artifacts, and
  human-readable diagnosis summaries
- dominant cards must earn their footprint; oversized low-information panels
  are a cockpit defect, not just a styling issue
- the first screen should prefer a dense decision strip over large mostly-empty
  blast-radius or next-action panels
- dead rail space should be converted into persistent operator context, not
  left as decorative empty area
- lower-half layout should adapt to decision density instead of holding a rigid
  symmetric grid
- singleton blocker cases should merge duplicate blocker surfaces and give more
  space to chain, stage, and proof context
- artifact priority filters should control which investigation surfaces are
  emphasized so the cockpit can shrink to the operator’s current depth of work
- the currently implemented scope hierarchy is:
  - campaign
  - iteration
  - stage
- chain-step focus should be severity-first by default:
  - highest-severity diagnosis first
  - then its chain step
  - then its pipeline stage
- ordered chain and stage surfaces are context, not the default focus rule
- current default iteration model is:
  - one job = one iteration
- family blockers are a first-class operator surface, but are currently derived
  in the dashboard adapter rather than emitted natively by the pipeline
- current limitation:
  - the package/campaign intake shell exists
  - native package/campaign execution is still pending unless a richer backend
    intake hook is added

## Missing Coverage Surfaces

The current cockpit is still missing several operator-visible coverage surfaces
that are required before a human should trust it as a campaign review product.

These gaps are product gaps, not merely styling gaps:

- no per-case function-flow coverage surface
  - the dashboard does not currently show:
    - authored expected function count
    - semantically aligned function count
    - uncovered function count
    - percent aligned for the selected case or chain
- no blocker-family coverage surface
  - the dashboard does not currently show:
    - which blocker families are represented across the active suite
    - which families are currently solved, partially solved, or still red
    - whether a medium or hard case is introducing a new blocker family or
      reproducing an existing one
- no state-initialization or lineage-materialization coverage surface
  - the dashboard does not currently show:
    - which required state producers have been proven
    - which shared-state handoffs are semantically aligned
    - which late consumers are still running on inferred, missing, or stale
      lineage

Until these surfaces exist, the cockpit can help with ranked diagnosis and
artifact triage, but it still cannot honestly present full suite-progress or
proof-coverage to a human operator.

## Future Capability Framing

When these suite-progress surfaces are added, the dashboard should not expose
them only as raw case ids or internal blocker-family labels.

A more useful product-facing capability framing is:

- `Surface Coverage`
  - how much of the authored expected function or checkpoint surface has been
    reached and semantically aligned
- `Workflow Coherence`
  - whether the product can keep a multi-step transaction or process logically
    connected from producer to downstream validator
- `Lineage Reuse`
  - whether emitted state, packets, receipts, or handles are being reused by
    later consumers as the same trustworthy business artifact
- `Branch Truth`
  - whether the product can preserve competing branches or replay paths until
    late truth is available instead of choosing a winner too early
- `Freshness / Stale-State Control`
  - whether the product can distinguish locally reusable state from state that
    has become globally stale or expired by the time late reconciliation runs

This framing makes suite progress understandable to a product owner, not just
to an engineer reading authored suite manifests.

## V1 Cockpit Goal

The dashboard must help a human operator quickly answer:

- what is broken
- why it is broken
- what changed
- what it broke downstream
- what to do next

If the screen cannot answer those questions cleanly, it is still a job monitor,
not yet a diagnostic cockpit.

## Scope Definitions

The cockpit must not use `stage` ambiguously.

- `chain step`
  - the authored campaign or DLL-step unit such as `01 Session Bootstrap` or
    `02 Reservation Stage`
- `pipeline stage`
  - the internal analysis stage such as `Analysis Entry`, `S00`, `S01`, and so
    on

Operator-facing labels may be cleaned for readability:

- raw ids like `02-reservation_stage` may render as `02 Reservation Stage`
- raw ids remain available in structured analysis and trace surfaces

The default operator story should therefore read like:

- `Reservation Stage failed at Analysis Entry`

not as a single ambiguous step/stage token.

## Operator And Agent Alignment

The dashboard and the agent must tell the same practical story.

That means:

- the operator summary I would point to in conversation should be the same
  summary the dashboard promotes first
- the analysis trace I would inspect to justify that summary should be visible
  beside it or immediately below it
- if the UI promotes one blocker while the deeper analysis actually uses a
  different blocker to choose the next move, that divergence is a product bug

The dashboard is not complete merely because the source routes exist. The UI is
only successful when:

- the source analysis I use
- the source analysis you can inspect
- and the summary the product presents first

all cohere into one readable decision surface.

## Operator Decision Contract

The primary unit surfaced to the human is a diagnosis object. The cockpit
should rank, explain, and link these diagnoses to canonical evidence.

Required diagnosis fields:

- `diagnosis_id`
- `title`
- `class`
- `severity`
- `trust_impact`
- `first_failing_stage`
- `first_failing_iteration`
- `affected_targets`
- `primary_evidence`
- `blast_radius`
- `recommended_next_action`
- `confidence`
- `owner_layer`

Canonical `owner_layer` values:

- `state`
- `contract`
- `capture`
- `measurement`
- `architecture`
- `plateau`
- `contradiction`

The dashboard should not force the operator to infer a diagnosis by combining
logs, badges, and artifact names mentally. The diagnosis object is the
decision-bearing contract.

## Audit-Derived Generic Requirements

The first real diagnostic audit against a multi-DLL system exposed several
generic cockpit requirements. These are not case-specific features. They are
implementation constraints for any honest operator dashboard.

### Verdict Hierarchy Must Be Explicit

The cockpit must distinguish these verdict layers instead of flattening them
into one generic green or red state:

- ingest success
- semantic success
- run validity
- validation completeness

These layers may disagree. The UI must not imply that one automatically proves
the others.

### The Cockpit Must Emit A Canonical Cause

A target or checkpoint may be:

- failed
- unknown
- locally green but globally untrusted

When the artifact set supports a likely cause, the cockpit should emit that
cause directly instead of forcing the human to infer it across multiple files.

### Primary Evidence Must Be Chosen Canonically

Every surfaced diagnosis needs one canonical `primary_evidence` pointer, with
additional artifacts treated as supporting evidence.

Without a primary evidence pointer, the cockpit still makes the human perform
manual artifact triage.

### Partial And Retry Runs Still Need Top-Level Rollups

The cockpit must not assume that only clean, completed runs deserve aggregate
summary artifacts.

Even when a run is:

- branch-local
- partial
- retry-focused
- continuation-scoped

the operator still needs a top-level rollup using the same diagnosis contract.

### Expected Surface And Extra Surface Must Be Separated

The cockpit must distinguish:

- expected contract-bearing exports
- required checkpoints for the current target or case
- additional discovered invocables outside the current proof obligation

This prevents wider module discovery from diluting the current diagnosis.

### Validation Failure Must Be Promoted, Not Buried

If behavioral or wrapper-based validation does not actually run, the cockpit
must surface that as a first-class diagnostic fact.

## First 30 Seconds

The first screenful must prioritize the most valuable operator information in
this exact order:

1. `top_blocker`
2. `trust_delta_vs_last_good`
3. `what_changed_this_iteration`
4. `blast_radius`
5. `recommended_next_action`
6. `supporting_evidence`

Stage bubbles, target lists, and recent jobs must not outrank those items.
Those are navigation and context surfaces, not the primary decision surface.

The first screen should also obey a density rule:

- if a card is visually large, it must deliver proportionate decision value
- empty or low-density cards should collapse, shrink, or move down
- evidence actions should not force the operator into raw JSON when a readable
  inline summary is possible
- the UI must visibly separate:
  - primary cause
  - secondary consequence
  - demoted downstream-only surfaces
- the first viewport should also preserve:
  - decision basis
  - chain steps
  - chain context
  - bounded ranked evidence
- when only one blocker family and one diagnosis are active, the next viewport
  should prefer:
  - investigation focus
  - stage detail
  - proof summary
  over duplicated family or diagnosis panels

The first viewport should also show chain progress clearly:

- completed predecessor steps
- the currently failing chain step
- downstream blocked or not-yet-run steps

Color semantics should be consistent:

- chain steps:
  - green = passed predecessor
  - red = current failing step
  - yellow = degraded or partial step
  - gray = downstream not run or not emitted
  - blue outline = selected focus when not failing
- pipeline stages:
  - red = active failing stage
  - green = completed stage with supportive evidence
  - yellow = partial, inferred, or trust-limited stage
  - gray = unreached or not emitted

## V1 Core Views

### Active Triage View

Primary goal:

- decide whether to stop, rerun, investigate, or fix

Primary surfaces:

- top blocker
- live trust risk
- current failing stage
- current blast radius
- next suggested action

### Completed Run Review View

Primary goal:

- understand what changed and whether the run produced useful evidence

Primary surfaces:

- run diff
- new verified functions
- regressions
- contradiction delta
- top artifacts
- review summary

### Campaign/System View

Primary goal:

- understand system shape, recurring blocker families, and where to spend the
  next investigation cycle

Primary surfaces:

- target hierarchy
- campaign diagnostics rollup
- recurring diagnosis families
- dependency shape
- freshness and readiness state

### Iteration View

Primary goal:

- understand one run as a bounded investigation pass between campaign and stage

Primary surfaces:

- iteration selector
- iteration summary
- verdict layers
- delta vs previous comparable iteration
- family blockers active in the selected iteration
- stage timeline scoped to the selected iteration

## V1 Core Surfaces

### Ranked Diagnostics Inbox

Purpose:

- make the highest-value problems visible first

Required content:

- title
- class
- severity
- trust impact
- stage
- target
- freshness
- linked artifacts
- suggested next action

Why it matters:

- it replaces a raw event stream with prioritized operator decisions

### Family Blockers

Purpose:

- surface the largest recurring issue families before the operator gets lost in
  one-off diagnoses

Required content:

- family id
- title
- severity
- affected diagnosis count
- affected stage count
- representative evidence
- recommended next move

Why it matters:

- it makes the highest-leverage issue clusters visible first
- it gives the operator a better bang-for-buck prioritization surface than a
  flat diagnosis list

### Run Diff Card

Purpose:

- show what changed relative to the most relevant trusted prior run or baseline

Required content:

- verified count delta
- regression count
- contradiction delta
- observer failure delta
- duration delta
- cost delta when available
- verdict-layer deltas for:
  - ingest success
  - semantic success
  - run validity
  - validation completeness

Why it matters:

- it answers "what changed this iteration" without manual run comparison

### Blocker-To-Blast-Radius Graph

Purpose:

- show how one failing prerequisite or contradiction propagates through the
  system

Required content:

- what failed first
- what depends on it
- what is now blocked because of it
- whether the failure is localized or systemic
- whether any apparently green downstream surface is only locally green and not
  yet globally trusted

Why it matters:

- it turns dependency shape into an actionable causal surface

### Trust Frontier Card

Purpose:

- summarize what the system currently believes and how trustworthy that belief
  is

Required content:

- verified
- inferred
- unresolved
- contradictory
- regressed
- safe to expose
- not safe yet

Why it matters:

- it gives the operator a stable trust summary instead of forcing trust
  judgments from scattered logs

### Artifact-Backed Stage Detail

Purpose:

- make each stage explainable in terms of inputs, outputs, blockers, and
  evidence

Required content:

- stage goal
- current target
- current iteration
- current status
- first failure within the stage when known
- stage inputs
- stage outputs
- top blockers
- top diagnostics
- relevant artifacts
- next suggested action

Why it matters:

- it turns stage selection into a decision surface instead of a decorative
  progress indicator

## Evidence And Trust Rules

Canonical emitted artifacts are required for blocker and regression diagnoses.
Raw event text alone is not sufficient as the primary evidence for a
decision-bearing diagnosis.

Current product truth:

- the dashboard is the primary product surface
- the dashboard may currently derive some operator truths from existing hooks
  when the pipeline does not yet emit them natively
- today, the most important still-derived layers are:
  - verdict hierarchy
  - validation completeness
  - causal summary
  - primary evidence selection
- because of that, the dashboard is authoritative for triage, but linked
  artifacts remain the final proof surface
- replacing any of those derived layers with pipeline-native truth is subject
  to explicit user approval and a same-change update to this README so the
  contract stays honest

Product rules:

- blocker and regression diagnoses must point to canonical emitted artifacts
- raw event text may support a diagnosis but may not be the primary evidence
- model-generated explanation may summarize or interpret evidence, but must not
  become the authoritative truth source
- weak evidence must surface as `low confidence` or `insufficient evidence`
  rather than fabricated certainty
- each diagnosis must select one canonical `primary_evidence` artifact before
  any secondary supporting artifacts are shown
- if a likely cause is supported by multiple artifacts, the cockpit should emit
  that cause as a first-class field instead of leaving it implicit across files
- validation non-execution, wrapper failure, or skipped behavioral checks must
  be surfaced as explicit evidence-quality warnings, not hidden in secondary
  reports
- raw `Open raw` or `Open source` actions are fallback inspection tools, not
  the primary evidence UX
- operator and agent alignment is a required product property

Every red thing in the UI should be clickable into evidence.

Every artifact should also roll back up into a ranked diagnosis.

The dashboard should prefer canonical emitted artifacts over frontend inference
or ad hoc model summaries. The preferred order is:

1. emit canonical red artifacts
2. display those artifacts clearly
3. optionally layer model-assisted explanation on top

Preferred canonical artifacts:

- execution trace
- runtime plan
- package truth
- cohesion report
- expected-versus-observed report
- observer summary
- checkpoint
- probe log

## Diagnostic Classes And Lifecycle

Canonical diagnostic classes:

- blocker
- warning
- regression
- contradiction
- observer failure
- missing prerequisite
- contract mismatch
- stage error
- readiness failure

Canonical diagnostic lifecycle states:

- `new`
- `active`
- `acknowledged`
- `resolved_by_newer_run`
- `regressed`
- `stale`

This lifecycle exists so the operator can tell whether a red thing is newly
introduced, still live, already understood, or reintroduced after being
resolved.

## Layout Contract

The dashboard should feel like a legacy-system triage cockpit rather than
generic pipeline telemetry.

Top row:

- health
- run status
- trust frontier
- delta vs last trustworthy run

Left rail:

- system target
- campaign target
- DLL or module family
- active iteration marker

Center pane:

- stage timeline
- selected-stage evidence
- next suggested action

Right pane:

- ranked diagnostics inbox
- blocker stack

Lower or secondary pane:

- dependency graph
- artifact tabs

## Required Backend Surfaces

### Existing

- `GET /api/fixtures`
- `POST /api/analyze-path`
- `GET /api/jobs/recent`
- `GET /api/jobs/{job_id}`
- `GET /api/jobs/{job_id}/events`
- `GET /api/jobs/{job_id}/invocables`
- `GET /api/jobs/{job_id}/mc-decisions`
- `GET /api/jobs/{job_id}/verdict`
- `GET /api/lab/status`

### Required Additions For V1

- `GET /api/dashboard/jobs/{job_id}/iteration-summary`
- `GET /api/dashboard/jobs/{job_id}/family-blockers`
- `GET /api/jobs/{job_id}/stage-summary`
- `GET /api/jobs/{job_id}/diagnostics`
- `GET /api/jobs/{job_id}/artifacts`
- `GET /api/jobs/{job_id}/verdict-hierarchy`
- `GET /api/jobs/{job_id}/validation-status`
- `GET /api/jobs/{job_id}/causal-summary`
- `GET /api/campaigns/{campaign_id}/summary`
- `GET /api/campaigns/{campaign_id}/diagnostics`
- `GET /api/targets`

## Hook Organization And Human Coverage

The dashboard should group hooks by what they do for the human operator. The
goal is to keep recovery, intake, triage, drilldown, and proof surfaces
separate enough that the UI stays navigable as more hooks are added.

### Health And Recovery Hooks

Purpose:

- decide whether the cockpit is trustworthy for live work
- recover from dead-lab states without leaving the dashboard

Current hooks:

- `GET /api/lab/status`
- `POST /api/dashboard/lab/restart`
- `GET /api/dashboard/hooks`

Human coverage:

- show whether the lab is healthy, degraded, or dead
- provide `Refresh Health` and `Restart Lab` as explicit recovery affordances
- turn a dead screen into a recovery console instead of a silent wall of 500s

### Job Selection And Intake Hooks

Purpose:

- move from no context to a selected target or fresh analysis run

Current hooks:

- `GET /api/fixtures`
- `POST /api/analyze-path`
- `GET /api/jobs/recent`
- `GET /api/jobs/{job_id}`

Human coverage:

- pick a job
- narrow the visible list with a text filter
- launch the current path-based intake hook
- re-open the current investigation surface after recovery
- keep the UI honest that enterprise package intake is the intended product
  entry even while the backend hook is still `analyze-path`

### Iteration Hooks

Purpose:

- make the middle scope between campaign and stage explicit

Current hooks:

- `GET /api/jobs/recent`
- `GET /api/jobs/{job_id}`
- `GET /api/dashboard/jobs/{job_id}/iteration-summary`

Human coverage:

- select the current iteration
- inspect one-job-as-one-iteration status, verdict layers, and delta
- keep stage work clearly subordinate to the selected iteration

### Triage Hooks

Purpose:

- deliver the first 30 seconds of operator value without forcing raw artifact
  review

Current hooks:

- `GET /api/dashboard/jobs/{job_id}/overview`
- `GET /api/dashboard/jobs/{job_id}/diagnoses`
- `GET /api/dashboard/jobs/{job_id}/run-diff`
- `GET /api/dashboard/jobs/{job_id}/trust-frontier`

Human coverage:

- top blocker
- trust delta
- what changed
- verdict-layer disagreement
- whether to stop, rerun, investigate, or fix

### Causal Drilldown Hooks

Purpose:

- explain where failure started, what it poisoned, and what the next move is

Current hooks:

- `GET /api/dashboard/jobs/{job_id}/stage-detail/{stage_id}`
- `GET /api/dashboard/jobs/{job_id}/blast-radius`
- `GET /api/jobs/{job_id}/events`

Human coverage:

- first failing stage
- local versus global trust
- blast radius
- evidence-backed next action

### Investigation Hooks

Purpose:

- let the operator dig deeper alongside the agent without dropping directly
  into raw logs first

Current hooks:

- `GET /api/dashboard/jobs/{job_id}/iteration-summary`
- `GET /api/dashboard/jobs/{job_id}/family-blockers`
- `GET /api/dashboard/jobs/{job_id}/diagnoses`
- `GET /api/dashboard/jobs/{job_id}/decision-basis`
- `GET /api/dashboard/jobs/{job_id}/evidence-stack`
- `GET /api/dashboard/jobs/{job_id}/stage-detail/{stage_id}`
- `GET /api/dashboard/jobs/{job_id}/blast-radius`
- `GET /api/findings/{job_id}`
- `GET /api/jobs/{job_id}/report`

Human coverage:

- hold one active diagnosis in focus
- explain why it matters in human-readable language
- surface the first failing stage, owner layer, primary evidence, and next move
- provide explicit source traces so the operator and agent can inspect the same
  hooks
- let the operator suppress lower-priority investigation surfaces through
  `Tier 1`, `Tier 2`, and `Tier 3` filters
- let the operator pivot from family blocker to diagnosis to stage of the
  selected iteration

### Proof Hooks

Purpose:

- move from cockpit triage to final artifact-level proof

Current hooks:

- `GET /api/findings/{job_id}`
- `GET /api/jobs/{job_id}/verdict`
- `GET /api/jobs/{job_id}/report`

Human coverage:

- confirm the diagnosis against emitted artifacts
- inspect the evidence behind any red or warning state

The dashboard should always prefer these hooks for final proof even when a
triage summary was derived.

## Surface Source Trace

The README should let a human trace each visible surface back to its source
hooks so the operator and agent can talk about the same underlying data.

### Left Rail

- `Recent Jobs`
  - `GET /api/jobs/recent`
  - dashboard-local text filter over the recent jobs payload
- `Iteration`
  - `GET /api/jobs/recent`
  - `GET /api/jobs/{job_id}`
  - `GET /api/dashboard/jobs/{job_id}/iteration-summary`
  - operator copy should prefer cleaned chain-step labels over raw component ids
- `Package Intake`
  - `GET /api/fixtures`
  - `POST /api/analyze-path`
  - dashboard-local intake-shape selector and fixture dropdown
- `Lab Control`
  - `GET /api/lab/status`
  - `POST /api/dashboard/lab/restart`
- `Hook Readiness`
  - `GET /api/dashboard/hooks`
- `Current Context`
  - `GET /api/dashboard/jobs/{job_id}/overview` -> `current_context`
  - required fields:
    - `chain_step_label`
    - `pipeline_stage_label`
    - active family
    - active diagnosis
- `Reading Order`
  - dashboard-local operator guidance for current cockpit density
  - dashboard-local current selection state:
    - active stage
    - active family
    - active diagnosis
    - active evidence tiers
- `Reading Order`
  - dashboard-local operator guidance

### First 30 Seconds Row

- `Top Blocker`
  - `GET /api/dashboard/jobs/{job_id}/overview`
  - `GET /api/dashboard/jobs/{job_id}/diagnoses`
- `Trust Delta Vs Last Good`
  - `GET /api/dashboard/jobs/{job_id}/overview`
  - `GET /api/dashboard/jobs/{job_id}/run-diff`
- `What Changed This Iteration`
  - `GET /api/dashboard/jobs/{job_id}/overview`
  - `GET /api/jobs/{job_id}`
- `Decision Cluster`
  - `GET /api/dashboard/jobs/{job_id}/overview`
  - `GET /api/dashboard/jobs/{job_id}/blast-radius`
  - dashboard-derived separation of:
    - primary cause
    - secondary consequence
    - demoted downstream-only surface
- `Chain Steps`
  - `GET /api/dashboard/jobs/{job_id}/iteration-summary` -> `chain_context.chain_steps`
  - dashboard-derived human-readable labels from:
    - `playbook_step`
    - `component_name`
    - authored Spectrum manifest ordering when available
  - presentation rule:
    - ordered chain context is always visible
    - selected focus remains severity-first
    - cleaned labels are operator-facing; raw ids stay in trace surfaces
- `Ranked Evidence`
  - `GET /api/dashboard/jobs/{job_id}/evidence-stack`
  - composed from:
    - `GET /api/jobs/{job_id}`
    - `GET /api/jobs/{job_id}/verdict-hierarchy`
    - `GET /api/jobs/{job_id}/causal-summary`
    - `GET /api/jobs/{job_id}/diagnostics`
    - `GET /api/jobs/{job_id}/validation-status`
    - `GET /api/findings/{job_id}`
    - `GET /api/jobs/{job_id}/report`
  - presentation rule:
    - inline previews first
    - `Open raw` second
    - only the top Tier 1 evidence should be visible by default
    - preview text must contain a concrete proving, missing, or empty signal
- `Decision Basis`
  - `GET /api/dashboard/jobs/{job_id}/decision-basis`
- `Chain Context`
  - `GET /api/dashboard/jobs/{job_id}/decision-basis` -> `chain_context`
  - `GET /api/dashboard/jobs/{job_id}/iteration-summary` -> `chain_context`
  - must distinguish:
    - `chain step`
    - `pipeline stage`

### Investigation And Review Surfaces

- `Iteration Summary`
  - `GET /api/dashboard/jobs/{job_id}/iteration-summary`
  - presentation rule:
    - compact grouped strips for run status, verdict layers, and delta
    - group `chain step` separately from `pipeline stage`
    - avoid tall sparse key/value layouts
- `Family Blockers`
  - `GET /api/dashboard/jobs/{job_id}/family-blockers`
  - may be merged into `Investigation Focus` when `layout_mode = singleton`
- `Investigation Focus`
  - `GET /api/dashboard/jobs/{job_id}/diagnoses`
  - `GET /api/dashboard/jobs/{job_id}/stage-detail/{stage_id}`
  - in singleton mode it also carries family-level summary and representative
    evidence
  - presentation rule:
    - narrative first
    - compact metadata chips second
    - trace sources last
- `Decision Basis`
  - `GET /api/dashboard/jobs/{job_id}/decision-basis`
  - source fields:
    - `promotion_basis`
    - `demoted_candidates`
    - `alignment_status`
- `Artifact Tiers`
  - static operator organization plus links to:
  - `GET /api/dashboard/jobs/{job_id}/overview`
  - `GET /api/dashboard/jobs/{job_id}/overview` -> `proof_summary`
  - `GET /api/dashboard/jobs/{job_id}/iteration-summary`
  - `GET /api/dashboard/jobs/{job_id}/family-blockers`
  - `GET /api/dashboard/jobs/{job_id}/run-diff`
  - `GET /api/dashboard/jobs/{job_id}/trust-frontier`
  - `GET /api/jobs/{job_id}/report`
  - `GET /api/findings/{job_id}`
  - `Proof Summary`
    - should explain current proof posture
    - should list strongest present proof and missing proof
    - should not degrade into counts-only chrome
- `Artifact Priority Filters`
  - dashboard-local tier state
  - controls visibility of right-hand investigation surfaces by importance
  - should stay compact and sit directly under artifact tiers
- `Ranked Diagnostics Inbox`
  - `GET /api/dashboard/jobs/{job_id}/diagnoses`
  - in singleton mode it should remain a compact confirmation card rather than
    a large independent work surface
- `Artifact-Backed Stage Detail`
  - `GET /api/dashboard/jobs/{job_id}/stage-detail/{stage_id}`
  - optionally filtered by family blocker in the current UI
  - in singleton mode this is the primary technical work panel
  - presentation rule:
    - compact definition grid for stage metadata
    - top stage evidence first
    - readable analysis rows by default
    - raw structured analysis only behind explicit expansion
- `Run Diff`
  - `GET /api/dashboard/jobs/{job_id}/run-diff`
- `Trust Frontier`
  - `GET /api/dashboard/jobs/{job_id}/trust-frontier`
- `Blocker To Blast Radius`
  - `GET /api/dashboard/jobs/{job_id}/blast-radius`
- `Stage Timeline`
  - `GET /api/jobs/{job_id}`
  - dashboard-local stage model
- `Event Log`
  - `GET /api/jobs/{job_id}/events`
- `Campaign/System View`
  - `GET /api/dashboard/campaigns/{campaign_id}/overview`

Where a surface is still derived today, that fact should remain visible in the
UI or README rather than hidden behind generic green or red wording.

## Hierarchy And Scope Views

The cockpit should support at least three nested scopes of analysis, and the UI
should adjust its summaries, panels, and density depending on which scope the
operator is viewing.

### Campaign Scope

Purpose:

- give the broadest picture of the current system or package campaign
- show the overall health of the investigation effort
- identify where time and budget should be spent next

Required surfaces:

- campaign summary
- recurring family blockers
- overall trust posture
- active iteration list
- top unresolved targets
- campaign-level artifact and evidence rollups

### Iteration Scope

Purpose:

- let the operator inspect one run or one investigation pass within the larger
  campaign
- understand what changed in that iteration relative to prior work

Required surfaces:

- iteration summary
- iteration verdict layers
- iteration delta against prior comparable run
- family blockers active in that iteration
- stage list for that iteration
- iteration-specific evidence and outputs

### Stage Scope

Purpose:

- provide the narrowest operational view
- explain what happened at one stage of one iteration and why

Required surfaces:

- stage goal
- stage inputs
- stage outputs
- stage-local blockers
- stage-local first failure
- stage-local evidence
- stage-specific next action

Product rule:

- campaign view should summarize broadly
- iteration view should compare and explain one pass
- stage view should narrow to one operational boundary
- switching scope should resize what the operator sees rather than simply
  reusing the same cards with different labels

## Family Blocker Priority

Family blockers are one of the highest-value operator concepts in the product.
The cockpit should continuously identify and rank the largest blocker families
so the team can get the highest leverage improvements first.

Purpose:

- avoid getting lost in one-off symptoms
- cluster related failures into the smallest useful improvement target
- maximize engineering return per fix cycle

Required behavior:

- surface recurring blocker families at campaign scope
- show which iterations are affected by each family
- show which stages are most associated with each family
- distinguish isolated findings from family-level structural issues
- use family blockers to drive next-action prioritization whenever possible

Examples of family-level concepts the cockpit should eventually support:

- state lineage failures
- contract mismatches
- capture or artifact gaps
- measurement gaps
- architecture bottlenecks
- contradiction clusters
- validation failures

## Pipeline Analysis Agents

Future cockpit and pipeline work should support more explicit model-assisted
analysis inside the pipeline itself, not just in the human discussion loop.

One important direction is adding more dedicated analysis agents that can
inspect how earlier artifacts are actually being used later in the pipeline.

Examples:

- audit how Ghidra output is consumed in later stages
- detect whether static analysis evidence was ignored, overridden, or degraded
- compare earlier and later interpretations of the same function or type shape
- detect criteria changes that materially alter trust, verdicts, or blocker
  classification

Product rule:

- these model-assisted agents must operate against explicit criteria and emitted
  artifacts, not free-floating intuition
- any new analysis agent that changes operator-visible truth should expose
  stable backend hooks and be reflected in the dashboard contract

## Deferred Implementation Notes

These ideas are now part of the dashboard contract even if they are not fully
implemented yet:

- campaign, iteration, and stage should be separate analysis scopes
- the UI should adapt to the current scope rather than showing one flat layout
- family blockers should be a first-class prioritization surface
- future pipeline analysis agents should help explain how evidence changes as it
  moves through later stages of the pipeline

## Placeholder-First Build Shape

If backend aggregation is not ready yet, the dashboard should still use
placeholder cards and payloads to lock the operator model and layout before the
full data surfaces exist.

Recommended center-pane placeholder cards:

- `Stage Goal`
- `Current Target`
- `Top Inputs`
- `Top Outputs`
- `Top Blockers`
- `Top Diagnostics`
- `Relevant Artifacts`
- `Next Suggested Action`

Recommended right-pane placeholder cards:

- `Blocking Diagnostics`
- `Warnings`
- `Recent Contradictions`
- `Observer Results`
- `Run Health`

Suggested temporary center-pane payload:

```json
{
  "stage_id": "s02",
  "stage_label": "Probe",
  "iteration_id": "run-003",
  "target_label": "contoso_config.dll",
  "campaign_id": null,
  "goal": "Probe unresolved parameters and gather trustworthy runtime evidence.",
  "inputs": [
    "seed findings loaded",
    "checkpoint restored",
    "3 unresolved exports"
  ],
  "outputs": [
    "2 successful probes",
    "1 contradiction",
    "updated finding set"
  ],
  "top_blockers": [
    "parameter role ambiguity on CFG_GetTicket"
  ],
  "top_diagnostics": [
    "bridge reachable",
    "runtime evidence present",
    "one observer failed"
  ],
  "relevant_artifacts": [
    "checkpoint.json",
    "probe-log.json",
    "observer-summary.json"
  ],
  "next_action": "Repair the failing prerequisite before spending a broader run."
}
```

Suggested temporary right-pane diagnostics payload:

```json
{
  "blocking": [
    {
      "title": "Missing prerequisite",
      "severity": "high",
      "detail": "Ticket-producing function has not produced a trustworthy handle."
    }
  ],
  "warnings": [
    {
      "title": "Bridge degraded",
      "severity": "medium",
      "detail": "Recent retries increased."
    }
  ],
  "observer_results": [
    {
      "title": "Lineage handoff observer",
      "status": "fail",
      "detail": "Expected downstream consumer to use same-run handle."
    }
  ]
}
```

## Product Patterns To Borrow

### Sentry

Pattern borrowed:

- issue grouping by fingerprint
- regression markers
- suspect-change hints
- inbox triage by severity and freshness

Why it matters:

- repeated contradictions and contract mismatches should collapse into stable
  operator issues rather than a noisy stream

### Datadog/Grafana

Pattern borrowed:

- subsystem health scorecards
- red/yellow/green status by subsystem
- trends over time
- summary-to-detail drilldown

Why it matters:

- trust, contradictions, observer failures, and retries need trend visibility
  and fast drilldown

### Honeycomb

Pattern borrowed:

- high-cardinality slicing
- cohort comparison
- filtering by run shape and conditions

Why it matters:

- the operator needs to isolate cohorts such as same DLL, same campaign, same
  graph epoch, same entrypoint, and same cache state

### Tracing Tools

Pattern borrowed:

- stage waterfall or timeline
- parent-child dependency context
- click-through into spans or steps

Why it matters:

- long or stuck stages should be visible as timing and dependency structure,
  not just a frozen stage badge

### CI Dashboards

Pattern borrowed:

- last-good comparison
- artifact tabs
- rerunnable failure context
- clear pass/fail delta surfaces

Why it matters:

- the pipeline already behaves like verification infrastructure and should show
  regression and baseline deltas that way

### Lineage/DAG Tools

Pattern borrowed:

- upstream/downstream lineage
- failed-node propagation
- readiness and freshness markers

Why it matters:

- prerequisite and dependency shape are central to the product story

## Current Dashboard State

What exists today in the dashboard:

- split dashboard shell:
  - [main.py](main.py)
  - [index.html](templates/index.html)
  - [dashboard.css](static/dashboard.css)
  - [dashboard.js](static/dashboard.js)
- header health chips for:
  - API
  - Bridge
  - Model
  - Storage
  - Lane
- explicit recovery controls:
  - `Refresh Health`
  - `Restart Lab`
  - dead-state banner when API or bridge is offline
  - proxy-side graceful `502` responses when the upstream pipeline disconnects
- left rail fixture target list backed by `/api/fixtures`
- `Analyze Path` launcher backed by `/api/analyze-path`
- recent jobs selector backed by `/api/jobs/recent`
- hook-readiness summary backed by `/api/dashboard/hooks`
- grouped hook catalog in the adapter layer for:
  - health and recovery
  - job selection and intake
  - triage
  - causal drilldown
  - proof
- first-30-seconds summary cards backed by:
  - `/api/dashboard/jobs/{job_id}/overview`
  - `/api/dashboard/jobs/{job_id}/run-diff`
  - `/api/dashboard/jobs/{job_id}/blast-radius`
- compact decision cluster separating primary cause, secondary consequence, and
  demoted downstream-only surfaces
- ranked evidence stack with inline previews backed by
  `/api/dashboard/jobs/{job_id}/evidence-stack`
- decision-basis alignment surface backed by
  `/api/dashboard/jobs/{job_id}/decision-basis`
- persistent current-context rail backed by dashboard overview plus current UI
  selection state
- chain-context panel in the first viewport backed by decision-basis and
  iteration-summary chain data
- ranked diagnostics inbox backed by `/api/dashboard/jobs/{job_id}/diagnoses`
- trust frontier backed by `/api/dashboard/jobs/{job_id}/trust-frontier`
- artifact-backed stage detail backed by `/api/dashboard/jobs/{job_id}/stage-detail/{stage_id}`
- campaign/system placeholder surface backed by `/api/dashboard/campaigns/{campaign_id}/overview`
- stage track retained as context and navigation
- event log retained as supporting context via `/api/jobs/{job_id}/events`

What the current implementation still leaves out:

- verdict hierarchy, validation completeness, causal summary, and primary
  evidence are still dashboard-derived rather than pipeline-native
- the dashboard should be used as the primary product surface for operator
  triage, but linked artifacts are still the final proof surface for those
  derived layers
- promoting any of those derived layers to pipeline-native truth requires
  explicit user approval and a README contract update in the same change
- dashboard recovery uses
  [restart_dashboard_lab.ps1](../sessions/restart_dashboard_lab.ps1)
  so the restart control targets the same bridge and API pair the cockpit reads
  from (`8090` and `8201`)
- run diff still uses a simple recent-job fallback instead of a true
  comparable baseline contract
- campaign/system view is still shallow and depends on whatever campaign
  payload the pipeline already exposes
- blocker-to-blast-radius is currently structured summary, not yet a richer
  causal graph
- stage detail is still derived from current artifacts rather than a native
  stage-summary route
- expected versus additional discovered surface is only inferred from current
  job runtime metadata and findings
- evidence previews and alignment status are dashboard-composed summaries over
  current native sources
- left-rail current context is dashboard-composed from adapter payloads and
  active UI state
- no decomposition view or deeper dependency-shape visualization yet

## Native Diagnostic Hooks

This tranche promotes five previously dashboard-derived surfaces into native
job routes:

- `GET /api/jobs/{job_id}/verdict-hierarchy`
- `GET /api/jobs/{job_id}/validation-status`
- `GET /api/jobs/{job_id}/causal-summary`
- `GET /api/jobs/{job_id}/diagnostics`
- `GET /api/jobs/{job_id}/artifacts`

These routes are now the preferred truth surfaces for operator-visible
diagnostics. The dashboard should consume them first and only fall back to
older adapter derivations when a route or underlying artifact is unavailable.

### Canonical Native Sources

Each native hook should remain traceable to emitted artifacts already produced
by the pipeline or saved session collector:

- `verdict-hierarchy`
  - `macro_verdict.json`
  - `run-validity.json`
  - `kpi_run.json`
  - `cohesion-report.json`
  - `validation-report.json`
- `validation-status`
  - `validation-report.json`
  - `human/validation-report.md` only as text fallback
- `causal-summary`
  - `stage-index.json`
  - `transition-index.json`
  - `cohesion-report.json`
  - findings only as supporting detail
- `diagnostics`
  - findings
  - `verdict-hierarchy`
  - `validation-status`
  - `causal-summary`
- `artifacts`
  - `artifact-index.json`
  - `human/l3-forensics-index.json`
  - `session-manifest.json`

## Side-By-Side Truth Model

Every native diagnostic hook must expose both:

- `operator_view`
  - concise, human-first, card-ready
  - what failed
  - why it matters
  - what to do next
- `analysis_view`
  - the structured evidence basis the agent uses
  - raw counts, stage ids, transition ids, conflict notes, and derivation data

Both views must point back to the same `source_artifacts` and `derived_from`
list so the operator and agent can inspect the same truth from different
densities instead of reading different systems.

The dashboard should show:

- operator summary first
- analysis trace beside it or immediately below it
- source artifacts clearly enough that a human can follow the explanation
- readable evidence summaries before raw route inspection buttons

Raw `Open source` actions are still useful, but they are fallback inspection
tools. They are not by themselves sufficient evidence UX.

The default visible analysis should be a readable structured summary first,
with raw JSON hidden behind an explicit expand affordance.

## Root Blocker Promotion

The cockpit must prefer the earliest trustworthy blocker over a downstream
absence caused by that blocker.

For example:

- if a job ends in `error`
- and findings, stage indexes, and other core artifacts were never emitted
- and validation is missing only because the run failed before that point

then the cockpit should promote:

- `analysis failed before discovery artifacts were emitted`

instead of:

- `validation completeness is broken or missing`

This rule applies to:

- `Top Blocker`
- `Blast Radius`
- `Family Blockers`
- `Artifact-Backed Stage Detail`

When stage truth is weak, the cockpit should use an honest weak coordinate such
as:

- `analysis-entry`

instead of implying a strong late-stage coordinate like `s06`.

Supporting evidence must be readable and ranked. It should explain:

- what the source is
- why it matters
- whether it is:
  - proving evidence
  - missing evidence
  - empty evidence
  - inferred fallback

Current dashboard rule:

- Tier 1 evidence is visible by default
- Tier 2 and Tier 3 are collapsed until the operator asks for deeper context
- empty findings or zero-function reports should render as explicit empty
  evidence previews, not just raw links

## Native Source Trace

The main cockpit surfaces should now read from these native hooks first:

- `Top Blocker`
  - operator-facing:
    - `/api/jobs/{job_id}/diagnostics` -> `operator_view`
  - analysis-facing:
    - `/api/jobs/{job_id}/diagnostics` -> `analysis_view`
  - root blocker rule:
    - prefer analysis-entry or artifact-emission failure over downstream
      validation absence when the run ended before core artifacts existed
- `Trust Delta Vs Last Good`
  - operator-facing:
    - `/api/jobs/{job_id}/verdict-hierarchy` -> `operator_view`
  - analysis-facing:
    - `/api/jobs/{job_id}/verdict-hierarchy` -> `analysis_view.layers`
  - derived fallback:
    - dashboard run-diff adapter until campaign-comparison-native surfaces exist
- `Blast Radius`
  - operator-facing:
    - `/api/jobs/{job_id}/causal-summary` -> `operator_view`
  - analysis-facing:
    - `/api/jobs/{job_id}/causal-summary` -> `analysis_view`
- `Iteration Summary`
  - operator-facing:
    - `/api/jobs/{job_id}/verdict-hierarchy` -> `operator_view`
  - analysis-facing:
    - `/api/jobs/{job_id}/verdict-hierarchy` -> `analysis_view`
  - derived fallback:
    - dashboard iteration-summary adapter for delta vs previous comparable run
    - dashboard chain-step and pipeline-stage grouping from current job payload
- `Chain Steps`
  - operator-facing:
    - `/api/dashboard/jobs/{job_id}/iteration-summary` -> `chain_context.chain_steps`
  - analysis-facing:
    - current job payload
    - predecessor fields
    - authored case manifests when available
  - derived fallback:
    - dashboard-generated blocked-downstream placeholder when full authored
      ordering is unavailable
- `Ranked Diagnostics Inbox`
  - operator-facing:
    - `/api/jobs/{job_id}/diagnostics` -> diagnosis `operator_view`
  - analysis-facing:
    - `/api/jobs/{job_id}/diagnostics` -> diagnosis `analysis_view`
- `Artifact-Backed Stage Detail`
  - operator-facing:
    - `/api/jobs/{job_id}/causal-summary` -> `operator_view`
  - analysis-facing:
    - `/api/jobs/{job_id}/causal-summary`
    - `/api/jobs/{job_id}/artifacts`
  - derived fallback:
    - dashboard stage-detail adapter until a native `stage-summary` route exists
  - weak coordinate rule:
    - use `analysis-entry` when the run failed before trustworthy stage-level
      artifacts existed
- `Supporting Evidence` and `Artifact Tiers`
  - operator-facing:
    - `/api/jobs/{job_id}/artifacts` -> `operator_bundle`
  - analysis-facing:
    - `/api/jobs/{job_id}/artifacts` -> `analysis_bundle`
  - evidence presentation rule:
    - evidence should be shown as readable ranked summaries, not just route
      labels

## Remaining Derived Seams

After this tranche, the critical truth surfaces are route-native, but some
dashboard summaries still remain derived:

- delta vs previous comparable iteration is still dashboard-derived because a
  native campaign comparison surface is not yet implemented
- family blockers are still grouped in the dashboard from native diagnoses
  rather than emitted as a first-class pipeline family-blocker route
- stage detail remains an adapter-level composition until a native
  `stage-summary` route exists
- adaptive `layout_mode`, merged-family behavior, and `proof_summary` are still
  dashboard-derived composition rules
- expected vs additional discovered surface is still partly inferred from job
  runtime metadata and findings
- decision-basis alignment status is still dashboard-derived from current
  native and adapter surfaces
- evidence-stack preview text is dashboard-composed from native routes and
  emitted artifacts

If any of those derived seams stay in the UI, the README and the UI must name:

- the exact source artifact or native route used
- what was derived from it
- what the operator should trust first

## Future Ideas: Mapping, Poison Analysis, And Suite Selection

These ideas are intentionally parked here as future cockpit work, not current
implemented behavior.

### Code Map And Human Map

The long-term engine goal is a trustworthy `code map`, but the cockpit also
needs a human-readable map that lets the operator understand the system without
opening raw internals first.

Future cockpit mapping surfaces should include:

- `code map`
  - machine-facing map of modules, stages, transitions, dependencies, emitted
    artifacts, and observed handoffs
- `human map`
  - readable summary of the same system at campaign, iteration, and stage scope
- `contract map`
  - expected producers, consumers, required checkpoints, and late-truth sites
- `evidence map`
  - which artifacts justify each conclusion and where trust is weak

The cockpit should eventually let the human and the agent inspect the same map
at different densities:

- campaign level
- iteration level
- stage level
- transition level

### Stage-By-Stage And Poison Analysis

The dashboard should eventually support explicit stage-by-stage analysis and
poison analysis.

`Poison analysis` means identifying where one broken or contaminated result:

- first appeared
- spread downstream
- changed later verdicts
- created false-green local surfaces
- should be isolated before broader reruns

Future poison-analysis surfaces should include:

- first poisoned stage
- poisoned transitions
- downstream surfaces carrying bad state
- locally green but globally untrusted stages
- recommended isolation or replay boundary

### Suite And Case Selection

The cockpit should eventually expose a first-class selector for curated suites,
packages, campaigns, and cases so both the operator and the agent can point at
the same target from the UI.

Future selector families should include at least:

- `Contoso` package and batch fixtures
- `Spectrum` reviewed challenge cases
- future enterprise package campaigns

The intended end state is:

- the human can choose a suite, package, campaign, or case from the UI
- the agent can reference the same chosen target and its emitted hooks
- the dashboard scope updates accordingly across campaign, iteration, and stage

### Current Reality

Today the cockpit does **not** yet have a native suite/case selector.

Current reality is:

- package-oriented intake shell exists
- current execution still routes through existing launch hooks
- saved jobs from Contoso, Spectrum, or future enterprise packages can still be
  reviewed by the cockpit after they run
- suite-aware selection is still a future UI surface

When suite-aware selection lands, the README should name:

- the source fixture or package manifest
- the launch hook used
- the emitted campaign or job ids
- the operator-facing summary surfaces that should update
- the analysis-facing traces that should stay aligned beside them

### Future Work: Operator Boundary And Continuation Visibility

The next missing cockpit layer is not more raw artifact links. It is an
operator-readable view of:

- where the current semantic seam broke
- what trustworthy context survived
- what the AI is recommending next
- why that next move outranks broader reruns

The operator should be able to make architecture decisions without doing raw
artifact archaeology, but still be able to challenge the AI's claim against
canonical evidence.

That means future cockpit work should expose these layers explicitly:

- `system seam`
  - the active dependency or handoff boundary under investigation
- `dll cluster / dependency slice`
  - the bounded family of DLLs participating in the current proof
- `last trusted checkpoint`
  - the most recent semantic obligation that still held
- `first failed checkpoint`
  - the earliest trustworthy point where the case contract broke
- `blocker family`
  - the current recurring failure class such as `lineage_materialization`
- `trusted predecessor context`
  - the prior jobs, targets, and artifacts that are still safe to reuse
- `next bounded retry`
  - the smallest follow-up run or fix scope that can reduce uncertainty

The intended operator/AI boundary is:

- AI should:
  - read large artifact stacks
  - compare expected versus observed behavior
  - classify the likely blocker family
  - propose the next bounded retry or fix target
- operator should:
  - decide whether the diagnosed blocker family merits a new system
  - decide whether the proposed next move is architecturally worth pursuing
  - audit whether the AI's claim matches the canonical evidence

So the cockpit should eventually show, by default:

- what was attempted
- what should have happened
- what actually happened
- where it first broke
- what evidence is still trustworthy
- what the next bounded move is

For continuation-aware runs, the dashboard should eventually surface the
semantic continuation ledger directly instead of leaving it buried in session
artifacts. At minimum that future surface should show:

- continuation id
- source iteration or run
- blocker family
- semantic checkpoint gap
- last success checkpoint
- first failed checkpoint
- trusted predecessor targets
- trusted predecessor job ids
- retry scope targets
- continuation status
- whether the latest continuation narrowed the gap

Without that layer, the AI can still operate, but the human remains too blind
to judge whether the pipeline is learning honestly or only producing more red
artifacts.

### Future Iteration: Enterprise-Scale Grouping

The current job and iteration surfaces are acceptable for small controlled
chains and per-DLL diagnosis, but they are not the final operator shape for
large enterprise systems.

For enterprise-scale package intake, the cockpit must not flatten hundreds of
DLLs into one long recent-job list. It must group and summarize first.

Future enterprise-scale surfaces should provide:

- one campaign or system viewer as the default entry point
- grouped blocker families across many DLLs
- grouped subsystem or cluster views before individual DLL views
- poison spread summaries showing where bad state or bad evidence first entered
- blast-radius summaries across many DLLs or stages
- iteration deltas across campaign waves, not only single jobs
- drilldown from:
  - campaign
  - to subsystem or blocker family
  - to iteration
  - to DLL
  - to stage
  - to artifact

Current honest limitation:

- the cockpit is currently good for small DLL sets and chained case analysis
- it is not yet the final grouped enterprise campaign viewer
- family blockers and iteration structure are the first building blocks toward
  that larger viewer

## Appendix A: Spectrum And Compiled Operator Examples

These examples are domain-specific operator readings. They are useful design
anchors, but they are not the generic v1 cockpit contract.

### Spectrum Compiled Operator Bundle

For compiled Spectrum runs, the UI should surface the same top-level operator
bundle used in review:

- `compiled-ingest-summary.json`
- `compiled-ingest-compare-report.json`
- `compiled-ingest.log`
- `heartbeats.json`
- per-DLL `runs/*` folders

The summary is the operator ledger for the case. It tells the human:

- which DLLs were uploaded
- which binary hashes were actually analyzed
- which semantic checkpoint each DLL was supposed to satisfy
- what chain carryover was supplied between DLLs
- whether validity gates passed
- what the per-run metrics were

The compare report is the contract verdict surface. It tells the human:

- whether binary ingest itself succeeded
- whether the design-contract semantic checkpoints aligned
- which symbols were merely discovered
- which symbols were semantically satisfied
- which checkpoint gaps still remain

The per-DLL run folders should stay directly accessible from the UI because
they contain the evidence behind the verdict:

- `findings.json`
- `verdict.json`
- `run_result.json`
- saved `session/` artifacts such as:
  - `cohesion-report.json`
  - `run-validity.json`
  - `verification-report.json`
  - `stage-index.json`
  - `artifact-index.json`

For Spectrum specifically, the dashboard should expose these operator fields
without requiring the human to open raw JSON first:

- case id
- proof class
- entry surface
- compiled target DLLs
- expected active modules
- expected execution flow
- expected symbol flow
- discovered symbol flow
- semantic symbol flow
- binary ingest proof verdict
- semantic alignment verdict
- semantic checkpoint gap
- per-DLL expected export
- per-DLL semantic checkpoint status
- per-DLL semantic checkpoint match
- per-DLL binary hash
- per-DLL session artifact presence

### Easy-01 Operator Reading

For compiled `easy-01`, the UI should show the intended chain:

- `SP_OpenOperatorSession`
- `SP_IssueReleaseHold`
- `SP_CommitRelease`
- `SP_RecordReleaseReceipt`

It should also show these exact top-level truths:

- `binary_ingest_proof_succeeded = true`
- `semantic_checkpoint_alignment_succeeded = true`
- `semantic_checkpoint_gap = []`

It should make clear that `easy-01` is green only for its bounded active chain,
not for the entire 11-DLL family.

### Medium-01 Operator Reading

For compiled `medium-01`, the UI should show the expected chain:

- `SP_OpenOperatorSession`
- `SP_IssueReleaseHold`
- `SP_PrepareReleasePreview`
- `SP_StageReleaseFeeQuote`
- `SP_VerifyReservedRelease`

It should make clear that the current honest verdict is:

- `binary_ingest_proof_succeeded = true`
- `semantic_checkpoint_alignment_succeeded = false`

The UI should expose the concrete gap, not just a red badge:

- `SP_PrepareReleasePreview = failure`
- `SP_StageReleaseFeeQuote = unknown`
- `SP_VerifyReservedRelease = failure`

That is what lets the operator see that the live blocker is semantic lineage
preservation across the fanout family, not binary ingest itself.

## Appendix B: Open Notes

The document should stay generic at the contract level and domain-specific in
appendices. Additional case-family examples should be added here rather than
blending them back into the main cockpit contract.
