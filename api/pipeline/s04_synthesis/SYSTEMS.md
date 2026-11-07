# S-04 Systems

## Depends On

| System | Use |
| --- | --- |
| LLM synthesis | Produces the narrative API reference. |
| Reconciled findings | Grounds synthesis in repaired evidence. |
| Coverage checks | Detects missing or under-covered functions in generated docs. |
| Micro-coordinator decisions | Captures post-synthesis init clues. |

## Does Not Own

| System | Boundary |
| --- | --- |
| Runtime proof | S-02/S-05 own observed and verified execution surfaces. |
| Schema patching | S-05 owns backfill into the schema. |
| Final closure | S-07 owns done/awaiting clarification state. |

## System Notes

Synthesis is useful narrative structure, not proof by itself. Runtime and
verification evidence outrank synthesis text.
