# S-03 Live Contract

## Guarantees Today

- Reconciles raw findings against probe evidence.
- Classifies write-function failures when MC-3 evidence is available.
- Emits or updates sentinel catalog and MC decision surfaces when applicable.

## Semantic Obligation

S-03 must turn raw probe/finding contradictions into cleaner status and failure
classifications. It repairs evidence interpretation; it does not create new
runtime observations.

## Handoff Rule

S-03 hands off corrected, reconciliation-aware findings to synthesis and
verification. Downstream stages should not have to rediscover obvious probe-log
contradictions.

## Advance Stay Fail

| Outcome | Current meaning |
| --- | --- |
| Advance | Findings are reconciled enough for synthesis. |
| Stay | Probe evidence is missing or too contradictory to repair locally. |
| Fail | Reconciliation cannot run or cannot preserve corrected findings. |

## Compatibility Notes

MC-3 artifacts are optional; absence means no MC-3 decision was emitted, not
that write failure analysis succeeded.

## Known Blocker Families

See `FAMILY-BLOCKERS.md` for S-03 blocker families classified as `handles`,
`detects_and_defers`, `unknown_or_not_owned`, and `architecture_gap`.
