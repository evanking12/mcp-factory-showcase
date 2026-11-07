# Migration Audit Role Map

## Purpose

This is the operator-facing role map for migration-shaped dynamic campaigns.

The mature dispatch shape is:

- review one ownership marker, seam, or claim ceiling at a time
- do not ask a subagent to review "the whole migration"
- keep branch choice with Codex as GM
- use subagents only when delegation is authorized and the trigger fits

## Marker Dispatch Rule

| Marker | Meaning | Primary audit pressure |
| --- | --- | --- |
| `red / owned` | Stage-owned implementation or contract changed. | Stage-owned code, contract, and artifact review. |
| `yellow / dependency` | Shared dependency used by stages changed. | Shared-system trace and hidden-consumer review. |
| `gray / upstream` | Intake, discovery, worker, runner, or feeder changed. | Feeder, lane, root, or inherited-artifact review. |
| `green / output` | Artifact, packet, schema, session, or emitted output changed. | Producer, packaging, consumer, and claim-ceiling review. |

## Active Roles

| Role | Why it matters now | Trigger | How to prompt | Expected output | Do not use when |
| --- | --- | --- | --- | --- | --- |
| `regression-governor` | Decides required tier, baseline, claim ceiling, and whether red still counts as bounded progress. | Runtime, pipeline, stage, compare, or gate policy changed; claim legality is unclear. | "Given this changed seam, baseline registry, validation output, and claimed success, decide required tier and legal claim ceiling." | Required gate tier, baseline, claim ceiling, unproven surfaces, next regression blocker. | The change is docs-only or already fully covered by a local Tier 0 check. |
| `system-contract-tracer` | Best role for yellow/gray questions: does the claimed system really connect across code, artifact, status, operator surface, and tests. | Shared dependency, upstream feeder, hidden consumer, or cross-surface contract changed. | "Trace this one system across code, artifacts, operator surfaces, and tests; say whether the claimed contract is implemented." | Supported/partial/unsupported trace with strongest gap and file/artifact evidence. | The issue is a single local code diff with no system boundary risk. |
| `verification_gate_bot` | Checks whether selected tests actually match the touched red/yellow/gray/green surfaces. | A tranche claims validation coverage, or test selection may be too weak. | "Given touched marker classes and intended claim, say what checks were required and whether they were run." | Required checks, satisfied checks, missing checks, justified confidence ceiling. | There is no claim being made yet and no verification choice to review. |
| `campaign-output-ledger` | Captures changed surfaces, branch-shaping facts, and breakage-map deltas during dynamic campaigns. | Prompt start for an active dynamic campaign with delegation authorized. | "Track structured campaign deltas for this tranche; return only writeback-ready updates." | Tranche summary deltas, breakage-map deltas, workflow friction, role/system candidate signal. | The work is not campaign-governed or delegation is not authorized. |
| `campaign-reviewer` | Pressure-tests whether prompt close, campaign closeout, and breakage-map reviewability are honest. | Prompt close, campaign close, pause, handoff, or context-pressure gate. | "Review this campaign checkpoint for workflow quality, stale truth, breakage-map honesty, and closeout readiness." | Review verdict, stale surfaces, workflow risks, closeout blockers. | Ordinary mid-prompt local work with no handoff or closeout gate. |
| `code_review_bot` | Needed for code-bearing red/owned or yellow/shared changes. | Code-bearing tranche touches stage-owned code or shared dependencies. | "Review this bounded diff for correctness, regression risk, boundary violations, and missing tests." | Findings ordered by severity with file/line evidence and test gaps. | Planning-only, docs-only, or no code diff exists. |
| `artifact-root-integrity-auditor` | Useful when baseline comparison or run outputs might be contaminated by stale roots or mixed sessions. | Real run output, session roots, inherited artifacts, or baseline roots are evidence-bearing. | "Audit whether the artifact roots are clean, comparable, and safe to use for the claim ceiling." | Clean/mixed/stale-root verdict, root evidence, claim ceiling impact. | No run/session artifact is part of the proof surface. |
| `proving-authority-reviewer` | Decides whether a rerun or regression gate is authoritative enough to steer branch choice. | A real rerun, proving command, or regression gate could affect next branch. | "Review this run or gate for authority, stale-lane risk, stale-code risk, capture integrity, and branch legality." | Authority verdict, trusted/untrusted evidence, legal claim ceiling, next proof blocker. | No rerun or proving-like command occurred. |

## Candidate Roles

| Candidate role | Trigger | Output | Current status |
| --- | --- | --- | --- |
| `baseline-breakage-map-auditor` | Migration tranche has validation output, red/green result, or changed claim ceiling. | Says whether `BASELINE-BREAKAGE-MAP.md` honestly explains changed surfaces, expected drift, unexpected breakage, owner attribution, blocker family, and claim ceiling. | Candidate role with contract and registry entry. |
| `stage-trace-blast-radius-auditor` | Stage migration touches `api/pipeline/sNN_*`, `api/pipeline/core`, routes, infra, or services. | Checks whether red/yellow/gray/green classification is correct and whether selected tests cover the touched surfaces. | Watchlist candidate; do not register until repeated evidence proves a split from `verification_gate_bot`. |
| `family-blocker-attribution-auditor` | A failure repeats or appears during a stage tranche. | Checks whether the failure belongs in `FAMILY-BLOCKERS.md`, `.agents/ARCHITECTURAL-WEAKNESSES.md`, or neither. | Watchlist candidate; likely split only if blocker attribution becomes frequent enough. |
| `handoff-packet-admission-auditor` | A stage emits or consumes a handoff packet. | Checks whether carry-forward, deferred, ambiguities, do-not-overread, coordination decision, and downstream targets are narrow enough. | Watchlist candidate; likely useful after more handoff packets exist. |
| `migration-claim-ceiling-auditor` | Before campaign closeout or push after migration work. | Checks whether claimed success exceeds tests or baselines actually run. | Watchlist candidate; likely absorbed by `regression-governor` unless evidence proves a separate role is needed. |

## Dispatch Rule

For migration-shaped campaigns, Codex as GM should perform one marker-driven
dispatch scan per tranche:

- identify touched red/yellow/gray/green surfaces
- map each marker to fitting active roles
- dispatch only when delegation is authorized and the role changes the next
  decision
- record skipped roles and reasons in dispatch accountability
- update the baseline breakage map when role output changes owner attribution,
  blocker-family attribution, claim ceiling, or next bounded fix target
