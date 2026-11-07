# S-01 Systems

## Depends On

| System | Use |
| --- | --- |
| S-00 handoff packet | Provides admitted setup/static context and `s01_targets`. |
| Executor/bridge runtime | Calls candidate init and write functions to test unlock behavior. |
| Sentinel semantics | Interprets blocking return codes from failed write attempts. |
| Checkpointing | Persists whether unlock has been resolved or deferred. |
| Finding persistence | Records successful unlock sequence steps as live findings when applicable. |

## Does Not Own

| System | Boundary |
| --- | --- |
| Static evidence extraction | S-00 owns static/setup packet production. |
| General function probing | S-02 owns broad per-function behavior discovery. |
| Final write-failure taxonomy | S-03 and later MC stages classify unresolved write failures. |
| Semantic truth synthesis | S-04 through S-07 own narrative synthesis, verification, and closure. |

## System Notes

S-01 should not become an archaeology stage. It should use the admitted packet
and fallback only for compatibility or repair.
