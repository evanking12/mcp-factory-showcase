# S-04 Live Contract

## Guarantees Today

- Synthesizes accumulated evidence into human-readable API documentation.
- May emit MC-4 init clue decisions when synthesis exposes cross-function patterns.
- May emit synthesis input and coverage surfaces for review.

## Semantic Obligation

S-04 must translate reconciled evidence into readable API synthesis while
preserving its dependence on upstream proof. It may infer structure, but it
must not replace verification.

## Handoff Rule

S-04 hands off narrative structure and inferred cross-function patterns. It
must remain grounded in reconciled evidence and should not replace verification.

## Advance Stay Fail

| Outcome | Current meaning |
| --- | --- |
| Advance | Synthesis exists or the pipeline has enough prior evidence to continue. |
| Stay | Reconciled findings are too thin for useful documentation. |
| Fail | Synthesis cannot run or generated documentation cannot be persisted. |

## Compatibility Notes

`api_reference.md` is a major human-facing artifact, but later verification and
harmonization can correct it.

## Known Blocker Families

See `FAMILY-BLOCKERS.md` for S-04 blocker families classified as `handles`,
`detects_and_defers`, `unknown_or_not_owned`, and `architecture_gap`.
