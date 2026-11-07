# S-05 Family Blockers

S-05 owns schema enrichment and verification distinction. It should classify
blockers around proof quality and schema backfill.

## handles

| Blocker family | Stage stance |
| --- | --- |
| schema lacks parameter descriptions after synthesis | Backfill where evidence supports it. |
| working-call claim needs verification | Verify or preserve unverified status. |
| custom positive return risks being overread | Keep verified and inferred outcomes distinct. |

## detects_and_defers

| Blocker family | Stage stance |
| --- | --- |
| partial verification coverage | Pass explicit partial status downstream. |
| read-to-write dependency clue | Emit MC-5 decisions when applicable. |
| verification blocked by unresolved precondition | Defer to S-06 or future rerun. |

## unknown_or_not_owned

| Blocker family | Stage stance |
| --- | --- |
| discovering new callable surfaces | Not owned; discovery/S-00 own setup surface. |
| resolving broad gaps | Not owned; S-06 handles gaps. |

## architecture_gap

| Blocker family | Stage stance |
| --- | --- |
| repeated false-positive verification | Requires stronger verification oracle or state-effect contract. |
| enrichment corrupts schema compatibility | Requires schema compatibility guard improvement. |
