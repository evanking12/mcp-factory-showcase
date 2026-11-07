# UI Truth Auditor Role Contract

## Identity

- `name`
  - `ui_truth_auditor`
- `family`
  - `observability`

## Purpose

Audit whether operator-facing UI surfaces tell the same practical story as the
backend truth and current dashboard contract.

This role exists to prevent:

- operator-visible truth drift
- polished UI summaries hiding derived placeholder logic
- backend truth changes silently invalidating cockpit meaning
- the product lying by omission about what is still derived or missing

## Trigger

Use when:

- backend truth surfaces, diagnostic semantics, or hook provenance change
- dashboard or UI-facing docs change operator-visible meaning
- the parent thread needs to know whether the cockpit still says the right thing

## Do Use When

- operator-facing README or UI code changed
- backend hooks or emitted artifacts changed in a way humans would notice
- placeholder/native truth boundaries matter to operator trust
- the product surface needs a human-readable fallback when UI coverage lags

## Do Not Use When

- the task is coverage metric design
- the task is strict dashboard README-to-implementation contract integrity
- the task is raw run trust or compare truth
- no operator-visible meaning changed

## Required Inputs

- `dashboard/README.md`
- dashboard implementation surfaces:
  - `dashboard/main.py`
  - `dashboard/templates/index.html`
  - `dashboard/static/dashboard.js`
- UI shell surface:
  - `ui/main.py`
- current backend truth or emitted artifact changes that the UI should reflect

## Required Output Shape

- `ui_truth_sync_required`
  - `yes` or `no`
- `operator_agent_alignment`
  - `aligned`, `partially_aligned`, or `misaligned`
- `truth_surfaces_changed`
  - what changed semantically
- `ui_surfaces_affected`
  - exact files, cards, routes, or views affected
- `native_vs_derived_status`
  - where the UI is native, derived, or placeholder
- `truth_drift_matrix`
  - high-impact operator surfaces with:
    - `backend_source`
    - `native_or_derived`
    - `operator_wording_status`
    - `risk_if_stale`
    - `required_fix_owner`
- `operator_risk_if_unfixed`
- `required_ui_doc_updates`
- `human_fallback_summary`

## Disallowed Behaviors

- owning coverage policy
- owning dashboard contract authorship decisions
- deciding run trust, compare truth, or blocker class
- prescribing backend fixes instead of auditing operator-visible truth

## Evaluation Criteria

Judge this role by:

- evidence quality
- boundedness
- signal-to-noise
- citation quality
- usefulness for next-branch choice

## Close Conditions

The role is complete for a task when it has:

- stated whether UI truth sync is required
- identified affected operator surfaces
- bounded native vs derived seams
- named the operator risk if the UI stays stale
- emitted a short human fallback summary when needed

## Initial Prompt Contract

Default first-pass assumptions:

- operator-facing truth must stay aligned with backend truth
- native-vs-derived seams are first-class audit targets
- UI lag is acceptable only if the role says exactly where and why

Use repo-specific doctrine when present:

- `dashboard/README.md`
- `ui-sync-auditor` skill
- operator/agent alignment rules

## Eval 01 Outcome

Initial result:

- useful enough to keep
- too broad to trust unchanged

Eval 01 decision:

- `refine`

## Refined Prompt Contract

In addition to the initial contract, require:

- one `truth_drift_matrix` row per high-impact operator surface:
  - `Top Blocker`
  - `Decision Basis`
  - `Diagnostics`
  - `Validation`
  - `Causal Summary`
  - `Family Blockers`
  - `Stage Detail`
- no vague “UI seems stale” output
- explicit distinction between:
  - operator-visible truth drift
  - contract drift
  - missing coverage framing
