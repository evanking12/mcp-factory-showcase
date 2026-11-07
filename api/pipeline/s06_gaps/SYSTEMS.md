# S-06 Systems

## Depends On

| System | Use |
| --- | --- |
| Gap resolution | Retries unresolved functions with maximum context. |
| LLM reasoning | Builds final retry and clarification context. |
| Micro-coordinator decisions | Captures MC-6 final unlock analysis. |
| Status persistence | Stores remaining clarification questions. |

## Does Not Own

| System | Boundary |
| --- | --- |
| Initial probing | S-02 owns first-pass behavior discovery. |
| Verification | S-05 owns replay-based verification. |
| Final closure | S-07 owns done versus awaiting clarification. |

## System Notes

S-06 is a last-chance stage. It should not hide uncertainty; unresolved
questions must remain visible to finalization and the operator.
