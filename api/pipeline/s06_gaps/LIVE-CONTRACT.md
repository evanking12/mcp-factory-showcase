# S-06 Live Contract

## Guarantees Today

- Attempts gap resolution when enabled.
- Runs MC-6 final unlock reasoning when applicable.
- Generates clarification questions when unresolved uncertainty remains.
- Snapshots schemas around gap-resolution and clarification boundaries when possible.

## Semantic Obligation

S-06 must make unresolved uncertainty explicit by retrying, classifying, or
asking for clarification. It must not silently convert gaps into success.

## Handoff Rule

S-06 hands off explicit gap outcomes and remaining questions. It should not
silently convert unresolved uncertainty into success.

## Advance Stay Fail

| Outcome | Current meaning |
| --- | --- |
| Advance | Gap attempts and/or clarification state are recorded. |
| Stay | Inputs are too inconsistent to retry or classify. |
| Fail | Gap resolution corrupts status, schema, or persisted findings. |

## Compatibility Notes

Gap resolution may be disabled by runtime settings. Disabled gap resolution is
not a stage failure if the status reflects that configuration.

## Known Blocker Families

See `FAMILY-BLOCKERS.md` for S-06 blocker families classified as `handles`,
`detects_and_defers`, `unknown_or_not_owned`, and `architecture_gap`.
