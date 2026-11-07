# Proof Routing And Hard01 Focus

## Purpose

Hard01 pressure should not be hijacked by unnecessary local Easy01 or Medium01
end-to-end reruns. This note fixes the current proving posture before more hard
suite work.

## Current Posture

- Medium02 is the local king-of-hill proving ground.
- Easy01 and Medium01 remain defended baselines, but they are not default local
  E2E prerequisites for unrelated work.
- Full `lane_trust,easy-01,medium-01,medium-02` remains CI and promotion
  authority.
- Local debugging should prove the narrow claim first, then widen only when the
  claim requires it.

## Proof Routing

- `red`: Product truth, session capture, route authority, semantic authority,
  closeout, Gate V1, API runtime, bridge runtime, product contract helpers, or
  pinned baselines. Prefer targeted checkpoint/replay locally when possible;
  CI should run the full product baseline gate.
- `yellow`: Suite runners, Medium02 or Hard01 pressure, observability,
  diagnostics, or non-baseline proving harness changes. Use Medium02 or the
  touched suite locally; do not rerun Easy01/Medium01 E2E by default.
- `grey`: Docs, campaign artifacts, governance text, and review surfaces. Run
  fast checks, sticky docs, and change-admission checks unless the change edits
  registered testing policy.
- `green`: Clearly isolated non-runtime edits. Static checks are enough unless
  review finds hidden runtime coupling.

## Checkpoint Replay Rule

Checkpoint replay should become the preferred proof surface for targeted
downstream repairs. A useful checkpoint freezes upstream truth, replays one
changed seam, and emits before/after authority deltas for the fields deciding
the claim.

Checkpoint evidence is not product-green evidence by itself. It is the cheaper
way to prove that a local repair works before spending full E2E budget.

The first narrow replay surface is
`scripts/regression/replay_session_closeout.py`: copy a trusted session,
recompute saved-session closeout on the copy, and compare before/after authority
without rerunning the suite.

Red/yellow routing still starts with seam-local proof when the seam is
isolatable. A Medium02, Hard01, Hard02, full product-suite, or Gate V1 rerun
requires an explicit `full_rerun_justification` unless the rerun is strictly
confirmation, promotion, baseline evidence, or the only trustworthy proof
surface left.

Anchor choice is not automatic:

- use Medium02 for general product-route/shared-code confidence
- use Hard01 for hard-family enterprise-survivability confidence
- use the touched suite for suite-local pressure
- use no anchor when checkpoint or target-local proof is the honest claim

## Observability Need

OpenTelemetry-compatible trace output is diagnostic-only. It should explain:

- where time went in long product-route runs
- where terminalization stalled
- whether save-session waited, retried, failed, or rejected
- whether a failure belongs to changed code, stale upstream state, harness
  setup, or unrelated baseline drift

Telemetry does not satisfy route authority, semantic proof, or product-green
eligibility.

## Immediate Campaign Order

1. `proof_routing_red_yellow_grey_green_v1`
2. `checkpoint_replay_for_targeted_repairs_v1`
3. `product_route_trace_and_closeout_visibility_v1`
4. `hard01_product_route_pressure_v1`

Hard01 can proceed sooner only if the completed routing work prevents local
Easy01/Medium01 reruns from blocking unrelated hard-suite pressure.

## Stop Conditions

- Do not build an observability platform before Hard01 pressure.
- Do not weaken product-green requirements to move faster.
- Do not run local Easy01/Medium01 E2E unless red-zone changes justify it.
- If checkpoint replay becomes too large, stop at the smallest useful seam
  replay and run Hard01 with the remaining caveat documented.
