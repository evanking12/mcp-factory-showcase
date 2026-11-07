# S-05 Systems

## Depends On

| System | Use |
| --- | --- |
| Synthesis/backfill | Extracts schema details from `api_reference.md`. |
| Runtime executor | Replays working calls for verification. |
| Finding persistence | Updates confidence and verification state. |
| Micro-coordinator decisions | Captures MC-5 chaining decisions. |

## Does Not Own

| System | Boundary |
| --- | --- |
| Initial behavior discovery | S-02 owns probing. |
| Reconciliation | S-03 owns deterministic repair before verification. |
| Final unresolved gap handling | S-06 owns last-chance retry and clarification generation. |

## System Notes

S-05 upgrades evidence quality. Verified behavior should be treated as stronger
than inferred behavior, but only within the scope actually replayed.
