# Live Checkpoint Observability

## Purpose

Long-running compiled checkpoint jobs must explain what they are doing while
they run. A CI step that only says `Run checkpoint` for many minutes is not
enough for this repo's migration pace.

This doctrine covers live diagnosis. It does not prove semantic correctness,
lane trust, or compiled-suite non-regression by itself.

## Required Live Observation

Each checkpoint poll should emit and preserve a compact observation with:

| Field | Meaning |
| --- | --- |
| `job_id` | Current pipeline job. |
| `phase` | Runner phase such as `analyze` or `explore`. |
| `stage` | Current pipeline stage when known. |
| `span` | Internal stage span when the stage exposes one. |
| `span_state` | `start`, `done`, or `fail` for the current span when available. |
| `span_message` | Current span-specific status message when available. |
| `message` | Current operator-facing status message. |
| `progress` | Current progress text. |
| `elapsed_seconds` | Time since this wait loop started. |
| `status_age_seconds` | Age of the status payload's own `updated_at` timestamp. |
| `status_stability_seconds` | Time since the status timestamp last moved. |
| `signature_stable_seconds` | Time since phase/stage/message/progress last changed. |
| `span_stable_seconds` | Time since the current stage span last changed when available. |
| `soft_stall_hint` | Non-fatal early warning, such as `s07_finalization_no_close`. |
| `claim_ceiling` | Always diagnostic-only unless a stronger gate also passes. |

## Operator Rule

Live observations should appear in GitHub Actions logs before hard timeout and
should be preserved in checkpoint artifacts. A failed checkpoint should tell the
operator the last observed stage, message, progress, stability age, and likely
stall family.

If those fields are missing, classify the result as observability debt before
claiming a product-stage regression.

## Current Soft-Stall Families

| Soft-stall hint | Meaning |
| --- | --- |
| `analyze_status_static` | Analyze status has not moved. |
| `s07_finalization_no_close` | The run reached finalization or harmonization but did not close. |
| `s07_<span>_no_close` | S-07 remained inside one internal span without visible close. |
| `<stage>_status_static` | A named stage has not changed its signature. |
| `<phase>_status_static` | The runner phase is static but no stage is known. |

Soft-stall hints must not fail a run by themselves. They exist to surface early
diagnosis before the hard timeout.

## What This Can Answer

- Which job, phase, and stage was active while CI appeared stuck.
- Which internal stage span was active when a stage exposes spans.
- Whether the visible status was moving or static.
- Whether a timeout likely belongs to finalization, a specific stage, analyze,
  or unknown lane/runtime behavior.
- What the next bounded investigation target should be.

## Future Expansion: Workflow Stage Checkpoints

Per-stage GitHub Actions checkpoint jobs are useful, but they are not the first
response to a vague long-running `Run checkpoint` step. The first response is
in-process stage span observability because it is cheaper and does not require
checkpoint/resume or artifact handoff between jobs.

Use workflow-level per-stage checkpoint jobs when span observability is still
not enough to localize stalls, or when checkpoint/resume and artifact handoff
are reliable enough that separate jobs improve diagnosis without creating
false CI noise.

For late closeout/session repairs, prefer the smaller
`scripts/regression/replay_session_closeout.py` surface first. It replays
saved-session closeout against a copied session directory and emits
diagnostic-only before/after authority deltas.

## What This Cannot Answer

- Whether the DLL behavior is semantically correct.
- Whether a compiled suite is non-regressed against a baseline.
- Whether a migration is complete.
- Whether a runtime proof is authoritative enough to steer branch choice.

Those claims still require the regression ladder, baseline comparison, and
proving-authority review surfaces.
