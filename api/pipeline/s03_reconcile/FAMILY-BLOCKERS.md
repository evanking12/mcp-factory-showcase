# S-03 Family Blockers

S-03 owns reconciliation of raw findings against probe evidence and write
failure classification when enough evidence exists.

## handles

| Blocker family | Stage stance |
| --- | --- |
| finding contradicts probe log | Repair or reclassify the finding. |
| uniform write sentinel pattern | Classify as likely global unlock/precondition blocker. |
| accidental success mislabeled as failure | Patch status when evidence supports it. |

## detects_and_defers

| Blocker family | Stage stance |
| --- | --- |
| mixed sentinels across write functions | Defer nuanced argument/precondition handling downstream. |
| insufficient probe evidence | Record inability to reconcile locally. |
| observed sentinel without catalog confidence | Preserve for later interpretation. |

## unknown_or_not_owned

| Blocker family | Stage stance |
| --- | --- |
| new runtime probing needed | Not owned; S-02 or rerun path must produce evidence. |
| final documentation wording | Not owned; S-04 owns synthesis. |

## architecture_gap

| Blocker family | Stage stance |
| --- | --- |
| repeated contradiction survives reconciliation | Requires stronger finding-status contract or reconciliation rules. |
| sentinel catalog cannot stabilize meanings | Requires reusable sentinel taxonomy/system improvement. |
