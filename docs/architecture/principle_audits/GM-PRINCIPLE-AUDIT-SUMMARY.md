# GM Principle Audit Summary

This summary includes only principles scoring `<7`.

## Family: `contract_coherence`

### `CC-02`: `explicit overlap resolution` — `6`

- what is directionally right:
  - `The repo already names overlap resolution as a real architecture rule and distinguishes keep, narrow, supersede, and retire behavior in doctrine.`
- what is risky or premature:
  - `The rule still lives mostly as prose. New decision-bearing surfaces can overlap for too long before their status is made explicit.`
- what should be preserved:
  - `The current doctrine in AGENTS.md and the architecture guide.`
- what should be constrained or tightened:
  - `Add one canonical overlap-resolution note or registry for new decision-bearing surfaces so overlap is recorded immediately instead of reconstructed later.`

## Family: `proving_economics`

### `PE-03`: `rerun gate law` — `6`

- what is directionally right:
  - `The five-gate rerun law is clearly written and campaigns often behave as if it matters.`
- what is risky or premature:
  - `The gates are not durably written often enough in actual rerun-bearing artifacts, which weakens auditability and makes legality look justified only in hindsight.`
- what should be preserved:
  - `The current five-gate doctrine and the strict lane-trust gate.`
- what should be constrained or tightened:
  - `Require a durable rerun_gate_result block before every expensive rerun and treat omission as governance failure.`

### `PE-05`: `no expensive loop doing multiple jobs at once` — `6`

- what is directionally right:
  - `The repo explicitly knows this is a bad pattern and has already created separate lane-trust and diagnostic loops to counter it.`
- what is risky or premature:
  - `Hard-family reruns still too often validate fixes, expose new blockers, and re-establish lane authority in the same spend event.`
- what should be preserved:
  - `The three-loop proving economics doctrine.`
- what should be constrained or tightened:
  - `Require one single_decision_job_of_this_rerun field before every expensive rerun and treat additional truths discovered by that rerun as spillover, not as proof that the rerun was well-scoped.`

## Family: `repo_hygiene_and_canonical_surfaces`

### `RH-04`: `setup/startup alignment` — `5`

- what is directionally right:
  - `The repo already names setup and startup surfaces as canonical and keeps the actual launcher scripts active and detailed.`
- what is risky or premature:
  - `SETUP.md materially lags start.ps1, which creates a direct trust break in the canonical-surface claim.`
- what should be preserved:
  - `The explicit canonical-surface rule naming SETUP.md, setup.ps1, and start.ps1.`
- what should be constrained or tightened:
  - `Update SETUP.md to match start.ps1 immediately and consider making launcher-facing doc sections generated or script-owned.`

## Family: `agentic_workflow_governance`

### `AW-07`: `event-bound dispatch law` — `6`

- what is directionally right:
  - `The event-bound dispatch law now exists explicitly in AGENTS.md and the dynamic-campaign templates.`
- what is risky or premature:
  - `The trigger law is still spread across templates and role notes instead of one structured canonical dispatch matrix. That makes it too easy to skip or delay mandatory roles and justify the omission later.`
- what should be preserved:
  - `The current event-triggered role list and the dispatch-accountability blocks in dynamic campaign artifacts.`
- what should be constrained or tightened:
  - `Extend AGENT-REGISTRY.json or add a dispatch-matrix artifact with mandatory_event_triggers, blocking_mode, and skip_conditions.`

## Repo-Wide Ranking

### Top 5 Weakest Principles

1. `RH-04 setup/startup alignment` — `5`
2. `CC-02 explicit overlap resolution` — `6`
3. `PE-03 rerun gate law` — `6`
4. `PE-05 no expensive loop doing multiple jobs at once` — `6`
5. `AW-07 event-bound dispatch law` — `6`

### Top 5 Strongest Principles

1. `DCG-01 active prompt canonical` — `9`
2. `DCG-05 explicit stop gate` — `9`
3. `OT-02 explicit authority surfaces` — `9`
4. `OT-04 compiled-binary proving vs architecture-proof separation` — `9`
5. `AW-01 GM of active truth` — `9`

## Cross-Family Recurring Failure Mode

The recurring failure mode is not missing doctrine. It is **enforcement lag**.
The repo often has the right rule in prose before it has the same rule as a
durable compact decision packet, a canonical registry field, or a single
operator-visible source of truth.

This appears as:

- overlap rules that are real but not centrally recorded
- rerun gates that are real but not durably written per rerun
- startup surfaces that are canonical in doctrine but not synchronized in docs
- event-bound dispatch that is explicit in templates but not yet a canonical
  structured governance table

## Recommended Next Doctrine Or Workflow Tightenings

1. `Add a structured overlap-resolution writeback surface for new decision-bearing artifacts and systems.`
2. `Add a required rerun-gate packet before every expensive hard-family rerun.`
3. `Add a required single-decision-job field for every expensive rerun.`
4. `Align SETUP.md with start.ps1 immediately.`
5. `Add structured event-bound dispatch metadata to the agent registry or an equivalent canonical dispatch matrix.`

## Follow-Up Status

The first doctrine follow-up slice now has canonical homes for these findings:

- `RH-04`
  - addressed through `SETUP.md` alignment with `start.ps1`
- `CC-02`
  - addressed through explicit overlap-resolution writeback fields in `AGENTS.md` and `CODEX-GOVERNANCE-SURFACES.md`
- `AW-07`
  - addressed through structured dispatch metadata in `AGENT-REGISTRY.json` and `AGENT-LIFECYCLE-GOVERNANCE.md`
- `PE-03` and `PE-05`
  - addressed through rerun-gate and single-primary-job writeback fields in `DYNAMIC-CAMPAIGN-ECONOMICS-LAW.md` and the dynamic tranche templates
