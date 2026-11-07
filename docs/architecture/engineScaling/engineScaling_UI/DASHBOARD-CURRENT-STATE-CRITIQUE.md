# Dashboard Current State Critique

## Purpose

This note captures the current operator-dashboard strengths, weaknesses, and
implementation gaps exposed by a live `Spectrum medium-01` run. It is intended
to serve as prompt material for the next cockpit implementation tranche.

The central question is not whether the dashboard has useful cards. It is
whether the dashboard is telling the operator the *most decision-useful truth
first*, with enough side-by-side analysis detail to justify that truth.

## Live Scenario Used For This Critique

The live specimen was the compiled `Spectrum medium-01` chain.

Observed chain behavior:

- `spectrum_session_bootstrap` completed successfully
- `spectrum_reservation_stage` failed on the next chained job
- downstream chain steps did not meaningfully execute

Current failing iteration:

- job id: `39712988`
- target: `spectrum_reservation_stage`

Observed job-level truth:

- `status = error`
- `message = Analysis failed`
- `error = Discovery produced no output files`
- process exit included `returncode=3221225786`
- `findings = []`
- report documented `0 functions`
- no meaningful stage or transition artifacts were emitted

## What The Dashboard Currently Gets Right

### 1. It makes missing trust visible

The current cockpit does succeed at showing that trust is weak:

- verification is empty
- verdict layers are mostly `unknown`
- causal evidence is missing
- validation status is absent

That is better than a false-green surface.

### 2. It preserves a side-by-side operator and analysis presentation

The addition of:

- `operator_view`
- `analysis_view`

is directionally correct. This supports:

- concise operator reading first
- inspectable evidence basis second

That is the correct long-term shape.

### 3. It has the right categories of surfaces

The dashboard already contains most of the correct surface classes:

- top blocker
- trust delta
- what changed
- blast radius
- recommended next action
- supporting evidence
- iteration summary
- family blockers
- stage detail
- artifact tiers

The issue is not absence of categories. The issue is prioritization and truth
selection within them.

### 4. It is already useful for small-chain debugging

For current DLL-scale work, the cockpit is already useful enough to expose:

- predecessor success
- current iteration failure
- downstream trust weakness
- missing emitted artifacts

That means the product is not failing conceptually. It is failing in the
quality of the first interpretation.

## What The Dashboard Currently Gets Wrong

## Root Problem

The dashboard currently overinterprets *missing downstream artifacts* as the
primary diagnosis, instead of promoting the *upstream analysis failure* that
caused those downstream absences.

In this live run, the cockpit surfaces:

- `Validation completeness is broken or missing`

as the top blocker.

That is not the most useful operator truth.

The more important truth is:

- `reservation_stage failed during analysis before discovery artifacts were emitted`

The validation failure is only a consequence of that.

### 1. Top blocker is not the true root blocker

Current top blocker:

- `Validation completeness is broken or missing`

Better top blocker:

- `Analysis failed before discovery artifacts were emitted`

Why this matters:

- validation can only be meaningful after analysis and exploration reach the
  point where wrapper or behavior validation is possible
- when analysis fails immediately, validation absence is not the primary
  blocker
- the operator needs the earliest root cause first

### 2. Trust delta is misleading

Current phrasing:

- `+0`
- `Verdict layers are aligned enough for operator use`

That is misleading for this run.

The layers are only "aligned" because they are mostly empty or unknown due to
artifact absence.

The better operator interpretation is:

- `No trustworthy delta can be computed because the iteration failed before core artifacts were emitted`

### 3. Blast radius is too literal and not decision-helpful

Current phrasing:

- `No affected stages or transitions were identified`

That is technically true from the absence of `stage-index.json` and
`transition-index.json`, but it misses the more useful operator reading:

- `The chain stopped at reservation_stage before downstream stages could be analyzed`

That is the real blast radius in this case.

### 4. Stage detail implies a stronger stage coordinate than the data supports

The cockpit currently shows a stage like `s06`, driven by validation logic.

That is misleading because the current run never reached a trustworthy late
stage failure. The job failed before meaningful stage-level artifacts were
emitted.

The better behavior would be:

- show `stage unresolved`
- or show `analysis-entry / pre-stage artifact emission`
- or explicitly mark the stage coordinate as inferred and weak

### 5. Family blocker grouping is using the wrong family

Current family blocker:

- `Validation failure`

More useful family for this run:

- `analysis-entry failure`
- `discovery/capture failure`
- `artifact-emission failure`

Why this matters:

- family blockers are supposed to tell the operator where leverage is
- if the family is misclassified, prioritization becomes distorted

### 6. Supporting evidence buttons are low-value

Current evidence buttons are mostly route labels:

- `Verdict hierarchy`
- `Causal summary`
- `Diagnostics`
- `Validation status`
- `Findings`
- `Report`
- `Session snapshot`

Problems:

- they are not clearly ranked by actual value for this run
- they do not summarize why each artifact matters
- they often dump raw route payloads rather than readable evidence
- they do not distinguish:
  - proving evidence
  - empty evidence
  - absent artifact proxies

The current evidence panel is therefore structurally correct but experientially
weak.

### 7. Empty analysis views are not being interpreted strongly enough

In this run:

- findings are empty
- report is empty
- artifact bundle is empty
- stage/transition causal surfaces are empty

Those empties are themselves strong evidence:

- the job failed before the expected analysis surfaces could materialize

The dashboard currently shows the empties, but it does not elevate their
meaning clearly enough.

## What Information Is Currently Going Overlooked

The most overlooked information is:

### 1. Predecessor-successor chain context

The operator should immediately know:

- previous iteration succeeded
- current iteration failed
- downstream steps were blocked by the current failure

Current dashboard behavior does not elevate that chain narrative enough.

### 2. Job-level error truth

The raw job record already contains a better root cause than the top blocker:

- `Analysis failed`
- `Discovery produced no output files`
- runtime exit with a specific failure code

That should outrank missing downstream validation or report artifacts.

### 3. Artifact absence as first-class evidence

Current run truth:

- no findings
- no report substance
- no stage index
- no transition index
- no validation report

The operator needs a compact interpretation such as:

- `expected analysis artifacts were not emitted`

That is more meaningful than a stack of empty cards.

### 4. Confidence and inference quality

The UI currently presents some inferred conclusions as if they were more
confident than they are.

Examples:

- stage assignment to a late validation stage
- cleanly named blocker family
- verdict layers being “aligned enough”

The cockpit should show confidence more explicitly whenever:

- a diagnosis is inferred from absence
- the route is partial
- the stage coordinate is unresolved

## How Good And Bad Should Be Decided

The cockpit needs a stricter hierarchy for deciding what counts as good or bad.

### Good

A run is good enough for operator trust when:

- the job reaches a meaningful terminal state
- core artifacts are emitted
- findings or a clean green proof exist
- stage and transition evidence exist
- validation is meaningful, not absent
- verdict layers are backed by emitted artifacts rather than empty fallbacks

### Bad

A run is bad in a high-priority way when:

- the job status is `error`
- analysis fails before artifact emission
- no findings are emitted
- no readable report is produced
- no stage or transition indexes are produced
- validation is absent because analysis never reached validation, not because a
  late validation disagreement occurred

### Worse Than Ordinary Bad

The cockpit should reserve top-priority emphasis for:

- root blocker
- chain interruption point
- missing artifact emission at expected trust boundaries
- poison entry point
- family blocker with high leverage

In this run, the root blocker is:

- early analysis failure

not:

- downstream validation absence

## What The UI Should Have Said For This Run

If the cockpit were telling the most decision-useful truth first, the main row
would read more like this:

### Top blocker

- `reservation_stage failed before discovery artifacts were emitted`

### Trust delta

- `No trustworthy delta available; iteration failed before core artifacts existed`

### What changed this iteration

- `session_bootstrap succeeded; reservation_stage failed at analysis entry`

### Blast radius

- `chain stopped before dispatch_preview, fee_quote, and settlement_reconcile could run`

### Recommended next action

- `inspect reservation_stage analysis failure and runtime crash before rerunning medium-01`

### Supporting evidence

- `job error`
- `stderr excerpt`
- `empty findings`
- `empty report`
- `missing stage/transition artifacts`

That tells the operator what actually matters.

## Strengths To Preserve

The next implementation prompt should preserve these strengths:

- side-by-side `operator_view` and `analysis_view`
- iteration framing
- family blocker framing
- artifact tier concept
- visible trace sources
- campaign-to-iteration-to-stage direction
- explicit native versus derived truth distinction

These are the correct building blocks. They should be improved, not removed.

## Weaknesses To Address Next

The next implementation prompt should explicitly address:

- promote root job failure above downstream artifact absence
- distinguish `root cause` from `downstream missing consequence`
- add predecessor and blocked-successor context to the top row
- treat artifact non-emission as a first-class diagnosis
- avoid overconfident stage assignment when stage evidence is missing
- improve blocker family classification for analysis-entry failures
- replace low-value evidence buttons with readable, ranked evidence summaries
- show confidence or inference quality when the dashboard is extrapolating from
  partial truth

## Design Principle Exposed By This Run

The most important design lesson from this run is:

- the first thing the operator sees must be the *earliest trustworthy blocker*,
  not the first downstream surface that happens to be missing

That principle should govern:

- top blocker selection
- family blocker grouping
- stage assignment
- evidence ranking
- next-action generation

## Candidate Next Prompt Themes

This note can be turned into an implementation prompt focused on one of these
themes:

### 1. Root blocker promotion

Teach the cockpit to prefer:

- job error
- analysis failure
- artifact-emission failure

over:

- missing validation
- empty report
- absent findings

when the latter are merely consequences.

### 2. Better evidence presentation

Replace raw evidence buttons with:

- a ranked evidence stack
- one-line human summaries
- explicit reason each artifact matters
- better handling for absent artifacts

### 3. Chain-aware campaign summary

Make the campaign read as:

- predecessor succeeded
- current iteration failed
- downstream iterations blocked

instead of showing a flatter job interpretation.

### 4. Artifact-absence diagnosis

Introduce an explicit diagnosis class for:

- `artifact emission failure`
- `analysis-entry failure`
- `discovery produced no usable outputs`

so these do not get mislabeled as validation failures.

## Current Bottom Line

The dashboard is already useful enough to expose that something is wrong, but it
is not yet telling the operator the *best* truth first.

For this run:

- the UI is partially truthful
- the UI is not yet correctly prioritized
- the root blocker is visible in the backend, but not yet promoted correctly in
  the cockpit

That is the implementation gap this note is meant to help close.
