# S-01 Family Blockers

S-01 owns write-unlock/precondition discovery for the current run. It should
classify recurring blockers here before they become generic downstream failures.

## handles

| Blocker family | Stage stance |
| --- | --- |
| init mode required before write | Attempt unlock probing and record result. |
| admitted S-00 packet missing or malformed | Fall back to legacy context without crashing. |
| write candidate classification needed | Classify enough write/init surface to attempt unlock. |

## detects_and_defers

| Blocker family | Stage stance |
| --- | --- |
| unlock still blocked after bounded attempt | Emit `write_unlock_probe.json` and defer to later MC stages. |
| ambiguous init sequence hints | Preserve context for S-03 through S-06 reasoning. |
| insufficient static target narrowing | Continue with fallback/broader unlock behavior; do not claim narrowed behavior. |

## unknown_or_not_owned

| Blocker family | Stage stance |
| --- | --- |
| per-function argument correctness | Not owned; S-02/S-03 handle probe and reconciliation. |
| cross-DLL unlock dependency | Not owned in current pipeline shape. |

## architecture_gap

| Blocker family | Stage stance |
| --- | --- |
| repeated unlock ambiguity without target narrowing | Requires stronger use of `s01_targets` or a dedicated unlock planner. |
| coordinator cannot decide deferred packet revival | Requires clearer admission/coordinator contract. |
