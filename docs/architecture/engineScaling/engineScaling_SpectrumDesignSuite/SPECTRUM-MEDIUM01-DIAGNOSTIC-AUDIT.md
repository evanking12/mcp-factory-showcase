# Spectrum Medium-01 Diagnostic Audit

## Summary

This note audits the real entry path and current diagnostic quality for
compiled Spectrum `medium-01`:

- case id:
  - `medium-01`
- case name:
  - `reservation_fanout_lineage`
- primary blocker family:
  - `lineage_materialization`

Reviewed evidence roots:

- compiled proof run:
  - `sessions/design_suite/compiled_ingest/spectrum_transaction_release_settlement_suite/medium-01/20260408-182513/`
- later failing branch:
  - `sessions/design_suite/compiled_ingest/spectrum_transaction_release_settlement_suite/medium-01/20260409-100044/`
- runtime-adoption truth surfaces:
  - `sessions/design_suite/runtime_adoption/spectrum_transaction_release_settlement_suite/medium-01/20260408-161443/`

This audit does not try to fix `medium-01`. It answers:

- how a DLL system enters the product today
- how the designed implementation says the case should behave
- where diagnostic truth is currently weak, conflicting, or misleading
- which weaknesses belong to the pipeline truth model versus later cockpit
  aggregation or presentation

Structured outputs for this audit live under:

- `sessions/design_suite/branch_decision/spectrum_transaction_release_settlement_suite/medium-01/20260409-diagnostic-audit/`

## Entry Trace Map

The real entry surface is:

- `upload`

The real entry runner is:

- `scripts/runs/run_spectrum_compiled_medium01.py`

That runner does not execute one monolithic system run. It performs chained
per-DLL runs, each constrained to one semantic checkpoint, using:

- `prior_job_id`
- `cross_dll_prior_job_ids`
- `selected_invocable_names`

The actual medium-01 chain is:

1. `session_bootstrap`
2. `reservation_stage`
3. `dispatch_preview`
4. `fee_quote`
5. `settlement_reconcile`

The chain plan is encoded in:

- `api/pipeline/core/spectrum_compiled_ingest.py`
  - `SPECTRUM_COMPILED_MEDIUM01_CHAIN_PLAN`

The package intake truth is split across:

- compiled package metadata:
  - `tests/fixtures/spectrum_transaction_release_settlement_suite/package_manifest.json`
- compiled DLL truth:
  - `tests/fixtures/spectrum_transaction_release_settlement_suite/truth_manifest.json`
- authored case truth:
  - `docs/architecture/engineScaling/engineScaling_SpectrumDesignSuite/SpectrumDesignSuite_Source/transaction_release_settlement_suite/cases/medium-01-manifest.json`

The end of the compiled entry path is:

- per-DLL `run_records` in `compiled-ingest-summary.json`
- aggregate semantic verdict in `compiled-ingest-compare-report.json`
- continuation emission via `emit_spectrum_medium01_semantic_continuation`

Operator reading:

- the product already has a real DLL-system entry path
- but that path is a stitched chain of bounded DLL runs, not yet a first-class
  system ingest diagnosis surface

## Designed Implementation Chain

The authored medium-01 contract says the intended transaction shape is:

- producers:
  - `session_bootstrap.open_operator_session`
  - `reservation_stage.issue_release_hold`
- shared state emitted:
  - `operator_token`
  - `reservation_handle`
  - `hold_token`
- direct consumers:
  - `dispatch_preview.prepare_release_preview`
  - `fee_quote.stage_release_fee_quote`
- late truth site:
  - `settlement_reconcile.verify_reserved_release`

Concrete authored handoffs:

- `reservation_stage.issue_release_hold` emits:
  - `reservation_handle`
  - `hold_token`
  - `operator_token`
- `dispatch_preview.prepare_release_preview` consumes:
  - `reservation_handle`
  - `operator_token`
- `fee_quote.stage_release_fee_quote` consumes:
  - `reservation_handle`
  - `operator_token`
- `settlement_reconcile.verify_reserved_release` consumes:
  - `reservation_handle`
  - `preview_ticket`
  - `fee_quote_id`

The core design pressure is not just "can the fanout consumers run." It is:

- can the reservation lineage survive honestly across both fanout consumers so
  that late validation remains trustworthy

The designed false-progress risk is:

- one consumer looks green locally
- but late validation still proves shared-handle lineage was not preserved

## Current Diagnosis Surfaces

The current diagnosis surfaces are real, but fragmented:

- compiled chain-level proof summary:
  - `compiled-ingest-summary.json`
- compiled chain-level semantic verdict:
  - `compiled-ingest-compare-report.json`
- authored-versus-runtime interpretation:
  - `spectrum-expected-observed-report.json`
- observer decision surfaces:
  - `spectrum-observer-summary.json`
- per-run human summaries:
  - `session/human/*.md`
  - `session/human/dashboard-row.json`

The system currently proves two different kinds of truths at once:

- binary ingest truth:
  - did the DLL chain upload and execute through the real lane
- semantic lineage truth:
  - did the medium-01 fanout preserve the authored lineage contract honestly

The problem is that those truths are not yet presented under one clean verdict
hierarchy.

## Diagnosis Matrix

The normalized diagnosis matrix for this audit is stored at:

- `sessions/design_suite/branch_decision/spectrum_transaction_release_settlement_suite/medium-01/20260409-diagnostic-audit/medium01_diagnosis_matrix.json`

High-level read:

- `SP_OpenOperatorSession`
  - operationally green
  - semantically aligned
  - not where the medium case becomes decision-bearing
- `SP_IssueReleaseHold`
  - semantically present but still only `inferred_success`
  - this is the shared-state producer, so trust here matters downstream
- `SP_PrepareReleasePreview`
  - appears locally reachable
  - but is explicitly flagged by authored artifacts as a false-green risk until
    late validation clears
- `SP_StageReleaseFeeQuote`
  - top-level status is `unknown`
  - deeper authored/runtime artifacts suggest a likely lineage break on the fee
    quote path
- `SP_VerifyReservedRelease`
  - late-truth checkpoint remains `failure`
  - it is the real trust site for medium-01, not just another downstream
    consumer

## Ranked Weakness Register

The structured weakness register for this audit is stored at:

- `sessions/design_suite/branch_decision/spectrum_transaction_release_settlement_suite/medium-01/20260409-diagnostic-audit/weakness_register.json`

### 1. Verdict hierarchy conflict

Why it ranks first:

- the operator can currently see a green top-level ingest proof while still
  encountering red or ambiguous validity and validation surfaces below it

Evidence:

- `compiled-ingest-compare-report.json`
  - `binary_ingest_proof_succeeded = true`
  - `semantic_checkpoint_alignment_succeeded = false`
- `compiled-ingest-summary.json`
  - per-run `valid_run = false` appears in the same proof bundle
- `session/human/dashboard-row.json`
  - later branch can say `run_valid = true` while still carrying
    `pipeline_verdict = "UNKNOWN"`

Why diagnostic analysis is weak:

- the current artifacts do not define which verdict dominates for which
  operator question

Operator risk:

- a human may mistake binary ingest success for trustworthy semantic success
  or mistake contract-valid local runs for globally trustworthy chain behavior

Fix owner:

- pipeline semantics

### 2. Wrapper-based validation weakness

Evidence:

- `session/human/validation-report.md`
  - `Checked: 0`
  - `wrapper_import_error:name 'Optional' is not defined`
- `session/human/l1-executive.md`
  - `Valid run: True`

Why diagnostic analysis is weak:

- the human-readable validation surface can imply healthy review posture even
  when actual wrapper-based validation did not happen

Operator risk:

- trust inflation
- false confidence that a behavioral surface was meaningfully checked

Fix owner:

- artifact generation

### 3. False-green risk is real but buried

Evidence:

- `spectrum-expected-observed-report.json`
  - overclaim on `dispatch_preview.prepare_release_preview`
- `spectrum-observer-summary.json`
  - `false_green` observer returns `warn`
  - next action says preview green should be treated as local only

Why diagnostic analysis is weak:

- the key product lesson is present, but it is trapped in secondary authored
  artifacts rather than promoted into the primary diagnosis

Operator risk:

- the cockpit may celebrate the first locally green consumer and hide the
  still-red late validator

Fix owner:

- dashboard aggregation

### 4. Fee quote causal story exists but is not canonical

Evidence:

- `compiled-ingest-compare-report.json`
  - `SP_StageReleaseFeeQuote = unknown`
- `spectrum-expected-observed-report.json`
  - `hold_token` missing from fee quote path
- `spectrum-observer-summary.json`
  - lineage preservation is only `partial`
  - missing lineage edge points at the fee quote path

Why diagnostic analysis is weak:

- the top-level semantic gap is real, but the most plausible causal story is
  still reconstructed by hand across multiple artifacts

Operator risk:

- the human sees `unknown` without an explicit first-class explanation of why
  that unknown likely exists

Fix owner:

- dashboard aggregation

### 5. Package metadata drift

Evidence:

- `package_manifest.json`
  - `proving_goal = compiled_easy01_ingest`
  - `selected_runtime_targets` remains easy-only
- medium-01 succeeds because code overrides with:
  - `SPECTRUM_COMPILED_MEDIUM01_CHAIN_PLAN`
  - bundled DLL fallback resolution

Why diagnostic analysis is weak:

- package-level metadata does not honestly describe the medium-01 proving
  surface the runner is actually executing

Operator risk:

- top-level package diagnostics can misstate what the current run was supposed
  to prove

Fix owner:

- pipeline semantics

### 6. Active retry branch lacks top-level rollup

Evidence:

- `sessions/design_suite/compiled_ingest/.../medium-01/20260409-100044/`
  contains:
  - `compiled-ingest.log`
  - `heartbeats.json`
- but no top-level:
  - `compiled-ingest-summary.json`
  - `compiled-ingest-compare-report.json`

Why diagnostic analysis is weak:

- the latest failing branch has detailed local artifacts but no canonical
  aggregate read

Operator risk:

- the human must inspect per-run folders manually and cannot compare the branch
  at the same abstraction level as the earlier compiled proof run

Fix owner:

- artifact generation

### 7. Extra-surface expansion can dilute case-bounded reads

Evidence:

- `compiled-ingest-compare-report.json`
  - `settlement_reconcile` discovers:
    - `SP_ConfirmAttestedRelease`
    - `SP_InvalidateStaleAttestedRelease`
    - `SP_SelectTrustedBranch`

Why diagnostic analysis is weak:

- extra discovered invocables are real, but they are not part of the bounded
  medium-01 proof obligation

Operator risk:

- case-bounded diagnosis can be diluted by unrelated future-surface discovery
  unless the cockpit clearly separates expected exports from additional
  discovered surface

Fix owner:

- dashboard presentation only

## Pipeline Truth Versus Cockpit Weaknesses

### Pipeline Truth Weaknesses

- verdict hierarchy conflict
- package metadata drift

These are upstream truth-model issues. If left unresolved, the dashboard can
only present cleaner confusion.

### Aggregation Weaknesses

- false-green risk buried in secondary artifacts
- fee quote causal story not canonical
- active retry branch lacks top-level rollup

These are cases where the evidence mostly exists, but there is no authoritative
joined diagnosis surface.

### Presentation Weaknesses

- extra-surface expansion dilutes the bounded case unless the UI explicitly
  separates expected versus additional invocables

This can be mitigated in the cockpit once the truth surfaces are stable.

### Borderline Case

- wrapper-based validation weakness

This starts as artifact generation because the emitted human validation surface
is misleading, but it becomes an operator-cockpit problem immediately if the
dashboard surfaces those fields without warning.

## Cockpit Readiness Checklist

The structured checklist is stored at:

- `sessions/design_suite/branch_decision/spectrum_transaction_release_settlement_suite/medium-01/20260409-diagnostic-audit/cockpit_readiness_checklist.json`

Current read:

- can the UI identify the first failing stage?
  - `no`
  - the causal failure is reconstructable, but not emitted as one canonical
    field
- can it identify the first failing iteration?
  - `no`
  - run ids and logs exist, but no joined diagnosis surface promotes first
    failure timing
- can it distinguish local green from globally trusted green?
  - `no`
  - false-green warnings exist, but not in the top-level verdict contract
- can it identify blast radius?
  - `partial`
  - observers imply fanout impact, but blast radius is not emitted as a primary
    operator object
- can it point to primary evidence?
  - `partial`
  - the artifacts exist, but the primary evidence is not selected canonically
- can it recommend next action?
  - `partial`
  - observer artifacts do, but top-level compiled proof surfaces do not
- can it distinguish ingest success, semantic success, artifact validity, and
  wrapper validation success?
  - `no`
  - these are the most dangerous overloaded verdicts in the current state

## Direct Product Reading

Medium-01 is already good enough to teach the product something important:

- the system can ingest a real DLL family through the upload lane
- the system can also preserve an honest semantic red state after ingest
- but the diagnostic model is still too fragmented to be a trustworthy
  operator cockpit without stronger joined evidence surfaces

The immediate product implication is:

- do not treat this as only a dashboard design problem

The next quality bar is:

- strengthen emitted diagnosis surfaces so the cockpit can present one clean
  causal read of medium-01 without forcing the human to reconcile five
  artifacts manually

## Direct Branch Implication

If this medium-01 audit is used to decide whether to branch:

- a dashboard-only branch would be premature

The first branch-worthy target is:

- strengthen medium-01 emitted diagnostics and verdict hierarchy

Why:

- the cockpit can only be as honest as the evidence and diagnosis contract it
  receives
- medium-01 already shows that the current contract is good enough to prove
  real product pressure, but not yet good enough to rank and explain that
  pressure cleanly for an operator
