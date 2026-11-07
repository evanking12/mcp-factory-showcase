# S-04 Family Blockers

S-04 owns evidence-grounded API synthesis. It should classify blockers around
documentation, coverage, and inferred cross-function patterns.

## handles

| Blocker family | Stage stance |
| --- | --- |
| reconciled evidence needs readable API documentation | Generate or refresh `api_reference.md`. |
| synthesis coverage needs auditability | Emit coverage/input snapshot surfaces when available. |
| init clue appears in synthesis context | Emit MC-4 clue decisions when applicable. |

## detects_and_defers

| Blocker family | Stage stance |
| --- | --- |
| evidence too thin for confident docs | Preserve caveats; downstream stages should not overread. |
| inferred dependency chain lacks runtime proof | Pass as clue, not truth. |
| documentation conflict with verification | Defer to S-05/S-07 correction. |

## unknown_or_not_owned

| Blocker family | Stage stance |
| --- | --- |
| verifying synthesized behavior | Not owned; S-05 verifies. |
| final closure and operator truth | Not owned; S-07 finalizes. |

## architecture_gap

| Blocker family | Stage stance |
| --- | --- |
| synthesis repeatedly invents unsupported semantics | Requires stronger evidence gates or synthesis input contract. |
| coverage cannot explain omissions | Requires better synthesis coverage artifact or review surface. |
